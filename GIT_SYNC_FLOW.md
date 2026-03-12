# Git Sync Flow for Two Machines

This document describes the recommended Git workflow to keep this project in sync across two different machines.

## Repository

- Remote: `https://github.com/henrikhansen-dhl/RepairShop`
- Main branch: `main`
- Primary local project folder: `/home/henrik/Projects/RepairShop`

## Daily Workflow

### 1) Start of work session (on either machine)

Always pull before making changes:

```bash
git pull --rebase origin main
```

Why: this makes sure your machine starts from the latest code from GitHub.

### 2) Do your coding work

Edit files as needed.

### 3) Save and commit your work

```bash
git add .
git commit -m "describe your change"
```

Tips:
- Use a clear commit message.
- Commit in small logical chunks when possible.

### 4) Push to GitHub

```bash
git push origin main
```

Why: this updates the shared source of truth so your other machine can pull the same changes.

### 5) Continue on the other machine

Before continuing work there, run:

```bash
git pull --rebase origin main
```

## Recommended Quick Cycle

Use this every time you switch machines:

1. Finish work on machine A:
   - `git add .`
   - `git commit -m "..."`
   - `git push origin main`
2. Start work on machine B:
   - `git pull --rebase origin main`

## If Pull Fails (Conflict)

If Git reports conflicts during `pull --rebase`:

1. Open conflicted files and resolve conflict markers.
2. Stage resolved files:

```bash
git add <resolved-file>
```

3. Continue rebase:

```bash
git rebase --continue
```

4. Push after rebase finishes:

```bash
git push origin main
```

If needed, cancel the rebase:

```bash
git rebase --abort
```

## Useful Status Commands

```bash
git status
git log --oneline -n 10
git branch -vv
```

## Files You Usually Do Not Want to Commit

Make sure your `.gitignore` includes machine/local artifacts such as:

```gitignore
.venv/
__pycache__/
*.pyc
db.sqlite3
.env
```

## One-Line Safe Start Command

```bash
git pull --rebase origin main && git status
```

## One-Line Safe Finish Command

```bash
git add . && git commit -m "your message" && git push origin main
```

Use the one-line finish command only when you are sure all current changes should be committed.
