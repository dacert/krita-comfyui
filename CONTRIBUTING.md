# Contributing guide

Patches and contributions are very welcome!

## Reporting issues

If you are facing an issue or want to report a bug, please check [existing issues](https://github.com/dacert/krita-comfyui/issues).

Having a look at the log files can provide additional information for troubleshooting. You can find them in the `.log` subfolder of the plugin installation folder (`krita_comfyui`).

When you open a new issue, please attach the log files. Other useful information to include: OS (Windows/Linux/Mac), Krita version, Plugin version, GPU vendor.

## Contributing code

For bigger changes, it makes sense to create an issue first to discuss a proposal before time is comitted.

You can submit your changes by opening a [pull request](https://github.com/dacert/krita-comfyui/pulls).

### Plugin development

The easiest way to run a development version of the plugin is to use symlinks:
1. `git clone` the repository into a location of your choice
1. `git submodule update --init`
1. in the pykrita folder where Krita expects plugins:
   * create a symlink to the `krita_comfyui` folder
   * create a symlink to `krita_comfyui.desktop`

### Code formatting

The codebase uses [ruff](https://docs.astral.sh/ruff/) for linting. You can
use an IDE integration, or check locally by running in the repository root:
```
ruff format
ruff check
```

### Code style

Code style follows the official Python recommendations. Only exception: no `ALL_CAPS`.

### Type checking

Type annotations should be used where types can't be inferred. Basic type checks are enabled for the project and should not report errors.

The `Krita` module is special in that it is usually only available when running inside Krita.

You can run [ty](https://docs.astral.sh/ty) from the repository root to perform type checks on the entire codebase. This is also done by the CI.

### Tests

There are tests, although with some caveats currently.

To install dependencies for tests run:
```
pip install -r requirements.txt
```
Tests are run from the project root via pytest:
```
pytest tests
```