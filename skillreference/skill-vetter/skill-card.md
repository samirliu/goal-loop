## Description: <br>
Security-first skill vetting for AI agents. Use before installing any skill from ClawdHub, GitHub, or other sources. Checks for red flags, permission scope, and suspicious patterns. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[spclaudehome](https://clawhub.ai/user/spclaudehome) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers and agents use this skill before installing or running third-party skills to review source, permissions, risk signals, and produce a structured vetting report. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Users may fetch or review skill content from unintended repositories if they copy placeholder GitHub commands without checking the target. <br>
Mitigation: Fetch only repositories intentionally selected for review and replace placeholders carefully before running lookup commands. <br>
Risk: Downloaded skill text may contain misleading or unsafe instructions. <br>
Mitigation: Treat downloaded skill text as untrusted content and review it before installation or execution. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/spclaudehome/skills/skill-vetter) <br>


## Skill Output: <br>
**Output Type(s):** [Markdown, Shell commands, Guidance] <br>
**Output Format:** [Markdown report with checklist items and optional bash examples] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Produces a manual vetting report; downloaded skill text should be treated as untrusted.] <br>

## Skill Version(s): <br>
1.0.0 (source: frontmatter and server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
