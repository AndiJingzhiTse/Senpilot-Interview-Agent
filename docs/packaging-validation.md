# ZIP packaging validation

Packaging was exercised entirely against saved retrievals and local fixtures. These checks did not open the public website or download its documents again.

## Saved retrieval checks

| Saved retrieval | Source status | Package result | Documents | ZIP bytes |
| --- | --- | --- | ---: | ---: |
| M12205 Other Documents, full request | complete | ready | 10 | 10371750 |
| M10431 Recordings, one sample | complete | ready | 1 | 392292513 |
| M12205 Transcripts | empty | no_files | 0 | No ZIP |
| M99999 Other Documents | not_found | no_files | 0 | No ZIP |
| Earlier M12205 run stopped by a row identity check | error | partial | 1 | 156559 |

Every published ZIP passed verification of its member list, embedded manifest, each document's size and SHA256, and CRC checks while reading entries back.
The package summary records the final archive's size and SHA256. A ZIP has one additional entry for `manifest.json` beyond its document count.
The source retrieval reports and document bytes are preserved.

The Recording source contained 471539706 bytes. Its ZIP remains about 392 MB, so compression does not make it suitable for ordinary email attachments.
The source WAV header warning remains in the manifest. Successful ZIP verification proves byte preservation, not that the source audio is complete or has been repaired.

## Automated checks

The suite ran 32 tests: 31 passed and one was skipped because this Windows session cannot create symbolic links without additional permission.
The skipped test checks a file symlink escaping the retrieval directory. Path traversal rejection and ordinary source containment checks were exercised; the actual symlink case remains unverified on this host.

The new packaging checks cover:

- Source and archive byte equality, full metadata, archive size, and SHA256.
- Repeated original filenames without collisions.
- Exclusion of unlisted files and incomplete transfers.
- Partial, failed, and interrupted retrievals retaining their failures and format warnings.
- Empty, unavailable, metadata only, and nonexistent matter results without an empty ZIP.
- Changed source contents, missing files, unsafe paths, duplicate identities, duplicate paths, and invalid counts.
- A ZIP with valid CRCs but deliberately incorrect document contents, rejected by SHA256 verification.
- Refusal to overwrite an existing package and removal of failed temporary archives.
- Automatic packaging from the retrieval CLI and partial exit status from the standalone packaging command.

Run the suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Python compilation, dependency checks, and Git whitespace checks also passed.
Email delivery, email encoding overhead, provider attachment limits, and remote file hosting remain outside this milestone.
