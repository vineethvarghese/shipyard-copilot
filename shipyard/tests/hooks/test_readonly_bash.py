import unittest

from helpers import HookTestCase

R = "shipyard:security-reviewer"
G = "shipyard:goldfish"
READONLY = ("shipyard:discovery", "shipyard:architect", "shipyard:planner", "shipyard:code-reviewer",
            "shipyard:security-reviewer", "shipyard:contract-reviewer", "shipyard:integration-reviewer",
            "shipyard:reliability-reviewer", "shipyard:simplicity-reviewer")


class Scope(HookTestCase):
    script = "readonly-bash.py"

    def test_non_shipyard_passthrough(self):
        self.assertAllowed(self.bash(None, "npm install && rm -rf build"))

    def test_authors_and_coordinator_not_covered(self):
        for agent in ("shipyard:implementer", "shipyard:verifier", "shipyard:coordinator"):
            self.assertAllowed(self.bash(agent, "npm install lodash"))

    def test_every_readonly_role_covered(self):
        for agent in READONLY + (G,):
            self.assertDenied(self.bash(agent, "rm -rf build"), "read-only")


class PackageInstalls(HookTestCase):
    script = "readonly-bash.py"

    def test_installs_denied(self):
        for cmd in ("npm install", "npm i lodash", "npm ci", "npm add x", "pnpm install", "pnpm add x",
                    "yarn", "yarn install", "yarn add x", "pip install requests", "pip3 install -r req.txt",
                    "python3 -m pip install x", "poetry add x", "cargo add serde", "cargo install ripgrep",
                    "go get example.com/x", "go install example.com/x@latest", "gem install rails",
                    "bundle install", "apt-get install -y curl", "apt install curl", "brew install jq",
                    "composer require x/y", "composer install", "cd sub && npm install"):
            self.assertDenied(self.bash(R, cmd), "read-only")

    def test_builds_and_tests_allowed(self):
        for cmd in ("npm test", "npm run build", "npm test -- --watch=false", "pnpm test", "yarn test", "pytest -q",
                    "python3 -m pytest tests", "go test ./...", "go build ./...", "go vet ./...", "cargo test",
                    "cargo build --release", "mvn -q test", "gradle test", "make test", "npm ls --depth=0",
                    "pip list", "pip show requests"):
            self.assertAllowed(self.bash(R, cmd))


class Git(HookTestCase):
    script = "readonly-bash.py"

    def test_state_changing_git_denied(self):
        for cmd in ("git commit -m x", "git merge x", "git rebase main", "git reset HEAD~1", "git checkout main",
                    "git switch main", "git stash", "git tag v1", "git branch tmp", "git branch -D tmp",
                    "git push", "git pull", "git fetch", "git add .", "git restore a", "git clean -fd",
                    "git -C . commit -m x", "git diff --output=out.txt"):
            self.assertDenied(self.bash(R, cmd), "git")

    def test_read_only_git_allowed(self):
        for cmd in ("git log --oneline -10", "git diff feature/x...feature/x-slice-01", "git show HEAD:README.md",
                    "git status --porcelain", "git rev-parse --abbrev-ref HEAD", "git ls-files", "git blame a",
                    "git branch -a", "git tag", "git tag --list 'v*'", "git stash list", "git grep -n foo",
                    "git config --get user.name", "git remote -v", "git merge-base main HEAD"):
            self.assertAllowed(self.bash(R, cmd))


class FilesAndRedirects(HookTestCase):
    script = "readonly-bash.py"

    def test_destructive_file_commands_denied(self):
        for cmd in ("rm a", "rmdir d", "mv a b", "chmod +x a", "chown me a", "truncate -s 0 a",
                    "dd if=/dev/zero of=a", "sed -i s/a/b/ f", "find . -name '*.tmp' -delete",
                    "find . -exec rm {} \\;", "xargs rm < list", "bash -c 'rm -rf x'", "echo $(rm x)",
                    "sudo ls"):
            self.assertDenied(self.bash(R, cmd), "read-only")

    def test_redirect_outside_ai_denied(self):
        for cmd in ("echo x > out.txt", "echo x >> src/a.ts", "ls | tee listing.txt", "cat a > /tmp/x",
                    "npm test &> log.txt", "echo x 1> out.txt", "cp a b", "touch new.txt"):
            self.assertDenied(self.bash(R, cmd), "outside .ai/")

    def test_safe_redirects_allowed(self):
        for cmd in ("npm test 2>&1 | tail -n 20", "ls missing 2>/dev/null", "echo x > /dev/null",
                    "echo note > .ai/planning/notes.md", "echo x >> .ai/planning/notes.md",
                    "git log | tee .ai/planning/log.txt", "grep -c '>' README.md", "echo 'a > b'",
                    "mkdir -p .ai/planning"):
            self.assertAllowed(self.bash(R, cmd))


class Network(HookTestCase):
    script = "readonly-bash.py"

    def test_mutating_requests_denied(self):
        for cmd in ("curl -X POST https://example.com/api", "curl -XDELETE https://example.com/x",
                    "curl --request PUT https://example.com", "curl -X patch https://example.com",
                    "curl -d '{}' https://example.com", "curl --data-binary @f https://example.com",
                    "curl -sd a=b https://example.com", "wget --post-data=a https://example.com"):
            self.assertDenied(self.bash(R, cmd), "read-only")

    def test_reads_allowed(self):
        for cmd in ("curl -s https://example.com/health", "curl -sS -H 'Accept: text/html' https://example.com",
                    "curl -X GET https://example.com", "wget -qO- https://example.com",
                    "curl -s -o /dev/null -w '%{http_code}' https://example.com"):
            self.assertAllowed(self.bash(R, cmd))


class Goldfish(HookTestCase):
    script = "readonly-bash.py"

    def test_read_only_commands_allowed(self):
        for cmd in ("ls -la", "cat README.md", "grep -rn cache src", "rg cache", "find . -name '*.ts'",
                    "git log --oneline", "git show HEAD", "git diff", "git ls-files", "wc -l README.md",
                    "head -n 5 README.md", "tail -n 5 README.md", "ls src | grep cache | wc -l",
                    "cat README.md 2>/dev/null"):
            self.assertAllowed(self.bash(G, cmd))

    def test_everything_else_denied(self):
        for cmd in ("npm test", "python3 -c 'print(1)'", "git status", "git blame a", "echo hi",
                    "cat a > .ai/x.md", "curl https://example.com", "ls | tee .ai/x", "rg --pre sh x",
                    "find . -exec cat {} +"):
            self.assertDenied(self.bash(G, cmd), "goldfish" if "goldfish" else "")


if __name__ == "__main__":
    unittest.main()
