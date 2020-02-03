# Drive Enhancement Proposals

DEP stands for Drive Enhancement Proposal.
A DEP is a design document providing information to the Drive community, or describing a new feature for Drive or its processes or environment.
The DEP should provide a concise technical specification of the feature and a rationale for the feature.

We intend DEPs to be the primary mechanisms for proposing major new features, for collecting community input on an issue, and for documenting the design decisions that have gone into Drive.
The DEP author is responsible for building consensus within the community and documenting dissenting opinions.

Because the DEPs are maintained as text files in a [versioned repository](https://github.com/nuxeo/nuxeo-drive/tree/master/docs/dep), their revision history is the historical record of the feature proposal.

## Start with an idea for Drive

The DEP process begins with a new idea for Drive.
It is highly recommended that a single DEP contain a single key proposal or new idea.
Small enhancements or patches often don't need a DEP and can be injected into the Drive development workflow with a patch submission to the [Drive issue tracker](https://jira.nuxeo.com/browse/NXDRIVE).
The more focused the DEP, the more successful it tends to be.
The DEP editors reserve the right to reject DEP proposals if they appear too unfocused or too broad.
If in doubt, split your DEP into several well-focused ones.

## Submitting a DEP

The proposal should be submitted as a draft DEP via a [GitHub pull request](https://github.com/nuxeo/nuxeo-drive/pulls).

The standard DEP workflow is:

- Create a file named `YYYY-MM Title.md` inside the folder `docs/dep/` that contains your new DEP.
- You should use this [template](0000-00%20Template.md) to be sure to have an overall idea of sections and required headers. You can add more sections for your needs.

Once the review process is complete, the DEP will be merged.

### DEP Status

DEP status are `draft`, `approved`, `rejected`, `ongoing implementation` and `implemented`.

`rejected` and `implemented` status are final, e.g. when one of those is set, the DEP cannot be modified later. Another DEP will be needed to apply changes to the current status.

## Security

When implementing, keep in mind that security is a critical part:

- Will you be introducing another third-party module? Is it the most secure?
- Have a look at the [OWASP top ten project](https://www.owasp.org/index.php/Category:OWASP_Top_Ten_Project) to ensure you will not introduce vulnerabilities.
