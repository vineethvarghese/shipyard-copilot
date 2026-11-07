import unittest

from helpers import FEATURE, SLICE, HookTestCase

C = "shipyard:coordinator"
I = "shipyard:implementer"
V = "shipyard:verifier"
R = "shipyard:code-reviewer"
D = "shipyard:discovery"


class PassThrough(HookTestCase):
    script = "protect-branches.py"

    def test_no_agent_type_allows_push(self):
        self.assertAllowed(self.bash(None, "git push origin main"))

    def test_non_shipyard_agent_allows_push(self):
        self.assertAllowed(self.bash("Explore", "git push --force"))
        self.assertAllowed(self.bash("other:coordinator", "git reset --hard"))

    def test_bad_stdin_allows(self):
        from helpers import run_hook
        self.assertAllowed(run_hook(self.script, None, self.repo.path, raw="not json"))

    def test_debug_log_only_when_enabled(self):
        quiet = self.bash(I, "git status")
        self.assertAllowed(quiet)
        self.assertEqual(quiet.stderr, "")
        loud = self.bash(I, "git status", env_extra={"SHIPYARD_HOOK_DEBUG": "1"})
        self.assertAllowed(loud)
        self.assertIn("[shipyard-hook:protect-branches]", loud.stderr)

    def test_non_git_command_allowed(self):
        self.assertAllowed(self.bash(I, "npm test && ls -la"))

    def test_quoted_git_text_is_not_a_command(self):
        self.assertAllowed(self.bash(I, "echo 'never run git push' | grep push"))
        self.assertAllowed(self.bash(I, "cat <<EOF\ngit push origin main\nEOF\n"))


class Push(HookTestCase):
    script = "protect-branches.py"

    def test_push_denied_for_every_shipyard_agent(self):
        for agent in (C, I, V, R, D):
            self.assertDenied(self.bash(agent, "git push"), "git push")

    def test_push_variants_denied(self):
        for cmd in ("git -C . push origin feature/x",
                    "FOO=1 git push",
                    "env GIT_TRACE=0 git --no-pager push",
                    "git status; git push",
                    "npm test && git push --force",
                    "git status || git push",
                    "true\ngit push",
                    "bash -c 'git push origin HEAD'",
                    "echo $(git push)",
                    "echo \"`git push`\"",
                    "timeout 30 git push",
                    "/usr/bin/git push",
                    "git -c alias.p=push p",
                    "git send-pack origin"):
            self.assertDenied(self.bash(C, cmd), "blocked")

    def test_configured_alias_resolved(self):
        self.repo.git("config", "alias.pp", "push")
        self.assertDenied(self.bash(C, "git pp origin"), "git push")

    def test_gh_pr_merge_denied(self):
        self.assertDenied(self.bash(C, "gh pr merge 12 --squash"), "gh pr merge")
        self.assertDenied(self.bash(I, "gh -R org/repo pr merge 12"), "gh pr merge")

    def test_gh_read_allowed(self):
        self.assertAllowed(self.bash(C, "gh pr view 12"))


class HistoryRewrite(HookTestCase):
    script = "protect-branches.py"

    def test_destructive_commands_denied(self):
        for cmd in ("git reset --hard HEAD~1", "git rebase main", "git cherry-pick abc123", "git am x.patch",
                    "git revert HEAD", "git filter-branch --all", "git update-ref refs/heads/main HEAD",
                    "git pull"):
            for agent in (C, I):
                self.assertDenied(self.bash(agent, cmd), cmd.split()[1])

    def test_soft_reset_and_read_only_git_allowed(self):
        self.assertAllowed(self.bash(I, "git reset HEAD src/a.ts"))
        for cmd in ("git log --oneline -5", "git diff feature/x...feature/x-slice-01", "git show HEAD",
                    "git status --short", "git rev-parse HEAD", "git ls-files", "git blame README.md"):
            self.assertAllowed(self.bash(R, cmd))


class Branches(HookTestCase):
    script = "protect-branches.py"

    def test_delete_feature_or_protected_denied(self):
        self.assertDenied(self.bash(C, "git branch -D feature/x"), "feature/x")
        self.assertDenied(self.bash(C, "git branch -d main"), "main")
        self.assertDenied(self.bash(C, "git branch --delete develop"), "develop")
        self.assertDenied(self.bash(C, "git branch -m main trunk"), "main")
        self.assertDenied(self.bash(C, "git branch -M feature/x feature/y"), "feature/x")

    def test_rename_current_feature_branch_denied(self):
        self.repo.checkout(FEATURE)
        self.assertDenied(self.bash(C, "git branch -m feature/renamed"), "feature/x")

    def test_coordinator_may_delete_other_branches_and_create(self):
        self.assertAllowed(self.bash(C, "git branch -d feature/x-slice-00"))
        self.assertAllowed(self.bash(C, "git branch feature/x-slice-02 feature/x"))

    def test_other_agents_may_not_create_or_delete(self):
        for agent in (I, V, R):
            self.assertDenied(self.bash(agent, "git branch tmp"), "only shipyard:coordinator")
            self.assertDenied(self.bash(agent, "git branch -D feature/x-slice-01"), "only shipyard:coordinator")

    def test_branch_listing_allowed(self):
        for agent in (I, V, R):
            self.assertAllowed(self.bash(agent, "git branch"))
            self.assertAllowed(self.bash(agent, "git branch --show-current"))
            self.assertAllowed(self.bash(agent, "git branch -a --list 'feature/*'"))

    def test_checkout_force_create_onto_protected_denied(self):
        self.assertDenied(self.bash(C, "git checkout -B main"), "main")
        self.assertDenied(self.bash(C, "git switch -C master"), "master")
        self.assertDenied(self.bash(C, "git switch -C develop"), "develop")
        self.assertDenied(self.bash(C, "git checkout -B release/2 HEAD"), "release/2")
        self.assertDenied(self.bash(C, "git checkout -B feature/x"), "feature/x")

    def test_coordinator_checkout_and_create_allowed(self):
        self.assertAllowed(self.bash(C, "git checkout feature/x"))
        self.assertAllowed(self.bash(C, "git checkout -b feature/x-slice-02 feature/x"))
        self.assertAllowed(self.bash(C, "git switch -c feature/x-slice-03"))
        self.assertAllowed(self.bash(C, "git checkout -B feature/x-slice-01 feature/x"))

    def test_other_agents_may_not_switch(self):
        for agent in (I, V, R, D):
            self.assertDenied(self.bash(agent, "git checkout feature/x"), "only shipyard:coordinator")
            self.assertDenied(self.bash(agent, "git switch main"), "only shipyard:coordinator")
            self.assertDenied(self.bash(agent, "git checkout -b tmp"), "only shipyard:coordinator")


class Commit(HookTestCase):
    script = "protect-branches.py"

    def test_implementer_and_verifier_commit_on_slice_branch(self):
        self.assertAllowed(self.bash(I, "git add src/cache && git commit -m 'slice 01 round 0: code'"))
        self.assertAllowed(self.bash(V, "git commit -m 'slice 01 round 0: tests'"))

    def test_implementer_and_verifier_denied_off_slice_branch(self):
        self.repo.checkout(FEATURE)
        self.assertDenied(self.bash(I, "git commit -m x"), SLICE)
        self.assertDenied(self.bash(V, "git commit -m x"), SLICE)

    def test_coordinator_never_commits(self):
        self.assertDenied(self.bash(C, "git commit -m 'slice 01: .ai state'"), "only merges")
        self.repo.checkout(FEATURE)
        try:
            self.assertDenied(self.bash(C, "git commit -m 'state'"), "only merges")
        finally:
            self.repo.checkout(SLICE)

    def test_ai_never_added(self):
        for agent in (C, I, V):
            for cmd in ("git add .ai", "git add -- .ai/slices/01/EVIDENCE.md", "git add -f .ai/state.json",
                        "git add ./.ai/PROJECT.md", "git add --force src/x"):
                self.assertDenied(self.bash(agent, cmd), "git add")
        self.assertAllowed(self.bash(I, "git add -- src/cache/a.ts"))
        self.assertAllowed(self.bash(V, "git add -- tests/cache/a.test.ts"))

    def test_commit_on_protected_denied_for_everyone(self):
        for branch in ("main", "develop", "release/1"):
            self.repo.checkout(branch)
            for agent in (C, I):
                self.assertDenied(self.bash(agent, "git commit -m x"), "protected branch '%s'" % branch)

    def test_commit_after_inline_switch_is_judged_on_new_branch(self):
        self.assertDenied(self.bash(I, "git checkout main && git commit -m x"), "git checkout")
        self.assertDenied(self.bash(C, "git checkout main && git commit -m x"), "protected branch 'main'")

    def test_other_agents_may_not_commit(self):
        for agent in (R, D, "shipyard:planner", "shipyard:architect"):
            self.assertDenied(self.bash(agent, "git commit -m x"), "may not commit")

    def test_missing_state_denies_commit(self):
        self.repo.remove(".ai/state.json")
        self.assertDenied(self.bash(I, "git commit -m x"), "state.json")

    def test_no_slice_branch_in_state(self):
        self.repo.set_state(activeSlice=None, sliceBranch=None)
        self.assertDenied(self.bash(I, "git commit -m x"), "sliceBranch")


class ReviewBypasses(HookTestCase):
    """Ways to move a protected branch found by the independent review."""
    script = "protect-branches.py"

    def test_fetch_into_local_branch_denied(self):
        for cmd in ("git fetch . feature/x-slice-01:main", "git fetch . +HEAD:refs/heads/main",
                    "git fetch origin develop:feature/x", "git fetch --update-head-ok origin"):
            self.assertDenied(self.bash(C, cmd), "fetch")

    def test_plain_fetch_allowed(self):
        for cmd in ("git fetch", "git fetch origin", "git fetch origin develop",
                    "git fetch origin refs/heads/develop:refs/remotes/origin/develop"):
            self.assertAllowed(self.bash(C, cmd))

    def test_worktree_on_protected_branch_denied(self):
        self.assertDenied(self.bash(C, "git worktree add ../w main"), "protected branch 'main'")
        self.assertDenied(self.bash(C, "git worktree add -b main ../w HEAD"), "protected branch 'main'")
        self.assertDenied(self.bash(C, "git worktree add ../w release/1"), "protected branch")
        self.assertAllowed(self.bash(C, "git worktree add ../w feature/x"))

    def test_git_after_cd_denied(self):
        self.assertDenied(self.bash(C, "cd ../w && git merge --no-ff feature/x-slice-01"), "after a `cd`")
        self.assertDenied(self.bash(I, "cd sub; git commit -m x"), "after a `cd`")
        self.assertDenied(self.bash(C, "git -c alias.m='!cd ../w && git merge --no-ff feature/x-slice-01' m"),
                          "after a `cd`")
        self.assertAllowed(self.bash(R, "cd src && git log --oneline -3"))

    def test_git_dir_and_work_tree_overrides_denied(self):
        for cmd in ("git --work-tree=/tmp --git-dir=../w/.git commit -m x", "GIT_DIR=../w/.git git commit -m x",
                    "env GIT_WORK_TREE=/tmp git merge --no-ff feature/x-slice-01", "git --git-dir ../w/.git reset --soft HEAD~1"):
            self.assertDenied(self.bash(C, cmd), "--git-dir")
        self.assertAllowed(self.bash(R, "git --git-dir=.git log -1"))

    def test_git_dash_c_is_resolved(self):
        self.repo.checkout("main")
        try:
            self.assertDenied(self.bash(C, "git -C %s commit -m x" % self.repo.path), "protected branch 'main'")
        finally:
            self.repo.checkout(SLICE)

    def test_reset_on_protected_branch_denied(self):
        self.repo.checkout("main")
        try:
            self.assertDenied(self.bash(C, "git reset --soft feature/x"), "protected branch 'main'")
            self.assertAllowed(self.bash(C, "git reset -- README.md"))
        finally:
            self.repo.checkout(SLICE)

    def test_symbolic_ref_repoint_denied(self):
        self.assertDenied(self.bash(C, "git symbolic-ref HEAD refs/heads/main"), "symbolic-ref")
        self.assertAllowed(self.bash(R, "git symbolic-ref HEAD"))


class NotesBranch(HookTestCase):
    script = "protect-branches.py"

    def test_notes_branch_never_checked_out_moved_or_deleted(self):
        for cmd in ("git checkout feature/x-shipyard", "git switch feature/x-shipyard",
                    "git switch -C feature/x-shipyard", "git branch -D feature/x-shipyard",
                    "git branch -f feature/x-shipyard HEAD", "git branch -m feature/x-shipyard other",
                    "git worktree add ../n feature/x-shipyard", "git update-ref refs/heads/feature/x-shipyard HEAD"):
            self.assertDenied(self.bash(C, cmd))

    def test_notes_branch_never_merged(self):
        self.repo.checkout(FEATURE)
        try:
            self.assertDenied(self.bash(C, "git merge --no-ff feature/x-shipyard"), "only the slice branch")
        finally:
            self.repo.checkout(SLICE)

    def test_snapshot_script_is_not_a_git_command(self):
        self.assertAllowed(self.bash(C, 'python3 "$CLAUDE_PLUGIN_ROOT/scripts/shipyard_state.py" snapshot -m "P9 slice 01 merged"'))


class Revert(HookTestCase):
    script = "protect-branches.py"

    def test_coordinator_reverts_on_feature_branch(self):
        self.repo.checkout(FEATURE)
        try:
            self.assertAllowed(self.bash(C, "git revert -m 1 --no-edit HEAD"))
            self.assertAllowed(self.bash(C, "git revert --abort"))
            for agent in (I, V, R):
                self.assertDenied(self.bash(agent, "git revert -m 1 HEAD"), "only shipyard:coordinator")
        finally:
            self.repo.checkout(SLICE)

    def test_revert_elsewhere_denied(self):
        self.assertDenied(self.bash(C, "git revert HEAD"), "only on the feature branch")
        self.repo.checkout("main")
        try:
            self.assertDenied(self.bash(C, "git revert HEAD"), "protected branch")
        finally:
            self.repo.checkout(SLICE)


class Merge(HookTestCase):
    script = "protect-branches.py"

    def setUp(self):
        super().setUp()
        self.repo.checkout(FEATURE)

    def test_coordinator_no_ff_merge_of_slice_allowed(self):
        self.assertAllowed(self.bash(C, 'git merge --no-ff feature/x-slice-01 -m "Merge slice 01: cache layer"'))
        self.assertAllowed(self.bash(C, "git merge --no-ff -m 'Merge slice 07: x' feature/x-slice-07"))

    def test_merge_abort_allowed(self):
        self.assertAllowed(self.bash(C, "git merge --abort"))

    def test_merge_requires_no_ff(self):
        self.assertDenied(self.bash(C, "git merge feature/x-slice-01"), "--no-ff")
        self.assertDenied(self.bash(C, "git merge --ff-only feature/x-slice-01"), "--ff-only")
        self.assertDenied(self.bash(C, "git merge --squash --no-ff feature/x-slice-01"), "--squash")

    def test_merge_source_must_be_slice_branch(self):
        self.assertDenied(self.bash(C, "git merge --no-ff main"), "only the slice branch")
        self.assertDenied(self.bash(C, "git merge --no-ff feature/y-slice-01"), "only the slice branch")
        self.assertDenied(self.bash(C, "git merge --no-ff feature/x-slice-01 feature/x-slice-02"), "exactly one")

    def test_merge_only_on_feature_branch(self):
        self.repo.checkout(SLICE)
        self.assertDenied(self.bash(C, "git merge --no-ff feature/x-slice-01"), "feature branch")
        self.repo.checkout("main")
        self.assertDenied(self.bash(C, "git merge --no-ff feature/x-slice-01"), "protected branch 'main'")

    def test_only_coordinator_merges(self):
        for agent in (I, V, R):
            self.assertDenied(self.bash(agent, "git merge --no-ff feature/x-slice-01"), "only shipyard:coordinator")


if __name__ == "__main__":
    unittest.main()
