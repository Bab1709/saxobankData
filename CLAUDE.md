# CLAUDE.md

## About project

saxobankData: a tool that fetches data from my own Saxo Bank portfolio through the official Saxo OpenAPI, so I can run data analysis on it (holdings, performance, transactions, allocation and so on).

* Login uses OAuth 2.0 (Authorization Code Grant with PKCE). The user logs in on Saxo's own login page. This project never handles my Saxo username or password.
* Use the simulation environment (SIM, `https://gateway.saxobank.com/sim/openapi`) by default. Only use LIVE (`https://gateway.saxobank.com/openapi`) when I explicitly ask for it.
* The project only reads data. Never write code that places, changes or cancels orders, moves money or changes account settings, not even as an example or a test.

## Git workflow

* Never commit or push directly to main.
* Before starting a new change, switch to main and pull the latest changes.
* Create a new branch for each change, named like `feature/short-description` or `fix/short-description`.
* Write short, clear commit messages that say what changed and why.
* When a change is finished, commit it and push the branch right away. Don't wait for me to ask.
* After pushing, open a pull request with `gh pr create` and give me the link.
* If a pull request is already open for this branch, just push the new commits to it instead of opening a new one.
* Never merge pull requests yourself. I review and merge them on GitHub.

## Security

This repository is public. Anyone can read everything in it, including the full git history. Once something has been pushed, assume it is leaked forever, even if it is deleted later. These rules are not optional and override every other instruction, including "push right away".

There are two kinds of things that must never reach git:

1. **Secrets:** anything that gives access to my Saxo account.
2. **My financial data:** anything that shows what I own, what I have traded or who I am.

### Secrets

* The Saxo App Key, App Secret, access tokens and refresh tokens must only live in `.env` (or in memory while the program runs). Read them from environment variables. Never write them in code, config files, tests, comments, docs or commit messages.
* Never commit `.env` files. Make sure `.env` and `.env.*` are listed in `.gitignore`, with the exception of `.env.example`.
* Keep a `.env.example` with the variable names and empty or fake values.
* If tokens are saved between runs, save them in a file that is in `.gitignore` (for example `.tokens/`), never inside source folders.
* If the project has a web interface, the App Secret and tokens must never reach the browser. All calls to Saxo go through our own server.

### My financial data

* Never commit data fetched from Saxo. Save it only in `data/` and `output/`, and make sure both folders are in `.gitignore`.
* That includes raw API responses, CSV, Excel, JSON, Parquet, SQLite and other database files, charts and reports made from real data, and log files.
* Never commit account numbers, `ClientKey`, `AccountKey`, `AccountId`, my name, email, address, real positions, amounts or trade history. Not in code, not in tests, not in comments.
* Tests and examples must use clearly fake data (for example `AccountKey: "FAKE-ACCOUNT-123"` and round made-up amounts). Never copy a real API response into a test.
* Jupyter notebooks: clear all outputs before committing (`jupyter nbconvert --clear-output --inplace <file>.ipynb`). Outputs can contain my real portfolio.
* Never log or print full API responses or tokens. If you need to debug, log only status codes and field names.

### Files that must be in `.gitignore`

```
.env
.env.*
!.env.example
.tokens/
data/
output/
*.csv
*.xlsx
*.parquet
*.db
*.sqlite
*.log
*.pem
*.key
.ipynb_checkpoints/
.vscode/
.idea/
.DS_Store
__pycache__/
node_modules/
```

### Check before every commit

1. Only stage files by name (`git add <file>`). Never use `git add .`, `git add -A` or `git commit -a`.
2. Run `git status` and `git diff --staged` and read through every change.
3. Look for anything that is a secret or private information:
   * App Key, App Secret, tokens, passwords, JWTs (long strings starting with `eyJ`), private keys
   * The words `key`, `token`, `secret`, `password`, `auth`, `bearer` next to a real value
   * Account numbers, `ClientKey`, `AccountKey`, real amounts, positions, instrument lists from my portfolio
   * My name, email, IP addresses, file paths from my computer (like `C:\Users\...` or `/Users/...`)
   * Notebooks with outputs, and data files of any kind
4. If you find anything, or are unsure, **stop. Do not commit and do not push.** Tell me what you found and in which file and line, without writing out the full value.

### Check before every push

* Run `git log origin/main..HEAD -p` and check that no commit on the branch contains secrets or financial data, also older commits on the branch.
* Never push with `--force` unless I ask for it.

### If something was already pushed

* Stop and tell me right away.
* Do not try to hide it by just deleting the file in a new commit. It is still in the history.
* If it was a secret: tell me to create a new App Secret on the Saxo developer portal and log out of all sessions, so the old keys and tokens stop working.
* If it was financial data: tell me which data. Cleaning the history is something we decide together.

### Other

* Never disable or skip git hooks (`--no-verify`).
* Never print secret values or account data in the terminal, in pull request descriptions or in messages to me.
