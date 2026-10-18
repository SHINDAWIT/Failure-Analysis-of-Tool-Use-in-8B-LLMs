# Local fixtures

Benchmark question payloads and gold answers are not included in the public repository. The archived runner expects the following local layout:

~~~text
fixtures/
  public/<When2Call uuid>.json
  private/when2call_answers.json
  loc_public/<Loc-Bench instance id>.json
  loc_private/answers.json
~~~

When2Call public fixtures contain the question and available tool definitions; the separate private file contains the reference action labels and target-tool metadata. Loc public fixtures contain the issue description and repository/base-commit information; the separate private file contains reference edit functions.

The archived preparation scripts show the expected field mapping. Their original local cache paths need environment-specific review. See [reproduction prerequisites](../../../docs/reproducibility.md).
