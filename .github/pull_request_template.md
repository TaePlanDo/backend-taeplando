# PR Readiness Checklist

Before requesting human review, every item below must be complete.

### 1. Does this already exist?

- [ ] Searched existing open/closed PRs, Linear issues, and the codebase for something similar
- [ ] Confirmed this doesn't duplicate existing work or something that could be extended instead

### 3. Thermo-nuclear code quality review

- [ ] Ran `/thermo-nuclear-code-quality-review` and resolved all findings
- [ ] No files pushed past 1000 lines without strong justification
- [ ] No spaghetti conditionals or ad-hoc special cases added to unrelated flows

### 4. Self-QA evidence

- [ ] Tested the change locally and verified it works
- [ ] Posted proof in this PR: screenshots, test output, screen recording, or step-by-step verification
- [ ] Tested edge cases and error states

---

## Jira

<!-- Required: link the Jira issue this PR addresses -->

PR title format: `TICKET_NAME feat/description`. example: `SCRUM-8 feat/add-new-feature`.
Jira link gets added automatically from the title.

## Problem Statement

<!-- What specific problem does this PR solve? Be specific about the issue. -->

## Root Cause

<!-- What was the underlying cause of this problem? -->

## Solution

<!-- Brief description of how this PR solves the problem -->

## How to QA

<!--
Step-by-step guide to validate this change:

1. What preconditions are needed?
2. What are the exact steps to reproduce/test?
3. What should happen at each step?
4. What edge cases should be tested?
-->

## QA Evidence

<!-- Drag & drop screenshots, paste test output, or link to a screen recording -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / code quality
- [ ] Documentation / infrastructure
