# CLAUDE.md

## About project

saxobankData: a tool that analyses my own Saxo Bank portfolio (holdings, returns, transactions, allocation and so on) from reports I export manually from SaxoTrader.

* There is no connection to Saxo. The project does not use the Saxo OpenAPI, has no login, no App Key, no tokens and makes no network calls to Saxo. Do not add any of that unless I explicitly ask for it.
* I export reports (Excel/CSV) from SaxoTrader and put them in `data/`. The code only reads files from `data/` and writes results to `output/`.
* Never write code that places, changes or cancels orders, moves money or changes account settings, not even as an example or a test.
* You may look at the column names and structure of files in `data/` to write parsers, but never print or quote the actual rows, amounts or account details.

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

1. **My financial data:** anything that shows what I own, what I have traded or who I am.
2. **Secrets:** anything that gives access to any of my accounts. The project should not need any, so if a secret ever shows up, that is a sign something is wrong.

### My financial data

* Never commit the reports I export from Saxo, or anything made from them. They live only in `data/` and `output/`, and both folders must be in `.gitignore`.
* That includes CSV, Excel, PDF, JSON, Parquet, SQLite and other database files, charts and reports made from real data, and log files.
* Saxo exports usually contain my name and account number in the file itself, so treat every exported file as private, even if it looks harmless.
* Never commit account numbers, `ClientKey`, `AccountKey`, `AccountId`, my name, email, address, real positions, amounts or trade history. Not in code, not in tests, not in comments.
* Tests and examples must use clearly fake data (for example `AccountKey: "FAKE-ACCOUNT-123"` and round made-up amounts). Never copy rows from a real export into a test.
* Jupyter notebooks: clear all outputs before committing (`jupyter nbconvert --clear-output --inplace <file>.ipynb`). Outputs can contain my real portfolio.
* Never log or print full rows of my data. If you need to debug, print only column names, data types and row counts.

### Secrets

* Never write passwords, keys or tokens in code, config files, tests, comments, docs or commit messages.
* Never commit `.env` files. Keep `.env`, `.env.*` and `.tokens/` in `.gitignore` as a safety net.

### Files that must be in `.gitignore`

```
.env
.env.*
.tokens/
data/
output/
*.csv
*.xls
*.xlsx
*.pdf
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
* If it was a secret: tell me which one, so I can change or revoke it right away.
* If it was financial data: tell me which data. Cleaning the history is something we decide together.

### Other

* Never disable or skip git hooks (`--no-verify`).
* Never print secret values or account data in the terminal, in pull request descriptions or in messages to me.
