# Production releases

This fork maintains standalone Python RTL-Davis production releases
independently of upstream releases.

## Versioning

- DRIVER_VERSION tracks the integrated upstream driver version.
- Custom production tags use vX.Y.Z-prod.N.
- Increment N for custom fixes without changing DRIVER_VERSION.
- Never move or reuse a published production tag.

## Release requirements

Before creating a production tag:

1. Review all changes.
2. Run the complete local regression suite.
3. Confirm all six GitHub Actions compatibility jobs pass.
4. Validate the extension package.
5. Complete live receiver validation.
6. Confirm the intended commit and rollback plan.

Creating a production tag triggers the release workflow. The workflow
runs the compatibility matrix before publishing the extension archive.

The Docker repository monitors published stable production releases,
vendors the driver at its resolved commit, records source checksums,
and opens an update pull request.

Publishing a release does not deploy it to a weather station.

## Upstream maintenance

Review upstream releases separately. Integrate and validate applicable
changes in this fork before publishing a new production release.

Do not replace the customized production driver directly with an
upstream release.
