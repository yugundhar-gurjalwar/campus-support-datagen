# Prompt history

Chronological record of the human prompts in the build session with Claude (Sonnet 5.5). Prompts are quoted verbatim
(including typos). Tool output and code are not repeated here; the repository's git history shows the resulting work.

## Prompt 1 — kick-off
> Hey claude I am giving you a problem statement, as a Sr. developer complete that project end-to-end. Use your expertise
> in everything you know and build it properly and then help me push it in my github by name -
> https://github.com/yugundhar-gurjalwar/. You have less then 6 hours to complete the entire project so without wasting
> any time let's go for it.

*AI response (summary):* noted that no problem statement was attached; explained it cannot push to GitHub from its sandbox
(no credentials, restricted network) and would instead deliver a push-ready repo with exact commands.

## Prompt 2 — problem statement + submission guidelines
> This is the problem statement and I have also attached submission guidelines document for your reference.

*Attachments:* `attachment.txt` (the synthetic-data problem statement: campus support routing / policy-grounded answers /
escalation; 10 granular generation steps) and `YottaFlex_AI_Candidate_Project_Submission_Guidelines.pdf` (72-hour window,
executable code, public repo with meaningful commits, transparent LLM use with prompt history, visible reasoning).

*AI response (summary):* read both documents, created a task list, and built the project end-to-end in the order recorded in
`git log` (scaffold + schema → master data + rules → simulator + anomalies → exporters/validator/evaluator/CLI → tests → docs →
datasets). The session hit an output-length limit once and resumed from the task list without changing direction.

## Notes for reviewers
- The guidelines ask for prompt history; this file is the complete set of human prompts from the session above.
  If additional sessions were used (e.g. follow-up edits), **append those prompts here**.
- Commit messages carry the `Co-Authored-By: Claude` trailer so AI involvement is visible per commit.
