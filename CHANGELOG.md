# auditwheel changelog

## HEAD

## 5.2.0

Released Oct. 22, 2022

### User-facing changes
- [FEATURE] Allow `auditwheel repair` to process multiple wheels ([#343](https://github.com/pypa/auditwheel/pull/343), [#62](https://github.com/pypa/auditwheel/issues/62))
- [FEATURE] Add `--exclude` option ([#368](https://github.com/pypa/auditwheel/pull/368), , [#76](https://github.com/pypa/auditwheel/issues/76), [#241](https://github.com/pypa/auditwheel/issues/241), [#391](https://github.com/pypa/auditwheel/issues/391))
- [FEATURE] Update `replace_needed` to reduce total calls to `patchelf` ([#376](https://github.com/pypa/auditwheel/pull/376))
- [FEATURE] Improve log message in case of NonPlatformWheel error ([#393](https://github.com/pypa/auditwheel/pull/393))
- [DOC] Update testing instructions ([#377](https://github.com/pypa/auditwheel/pull/377))

### Housekeeping
- fix: add `/auditwheel_src` to git safe directories ([#378](https://github.com/pypa/auditwheel/pull/378))
- test: add `manylinux_2_28` tests ([#369](https://github.com/pypa/auditwheel/pull/369))
- Updated action versions ([#384](https://github.com/pypa/auditwheel/pull/384))
- Update pre-commit hooks ([#399](https://github.com/pypa/auditwheel/pull/399))

## 5.1.2

Released Jan. 08, 2022

### User-facing changes
- [BUGFIX] wheels are not compressed with ZIP_DEFLATED ([#366](https://github.com/pypa/auditwheel/issues/366), [#367](https://github.com/pypa/auditwheel/pull/367))

## 5.1.1

Released Jan. 03, 2022

### User-facing changes
- [BUGFIX] building from a github archive fails ([#321](https://github.com/pypa/auditwheel/issues/321), [#361](https://github.com/pypa/auditwheel/pull/361))
- [BUGFIX] include tests in SDist ([#321](https://github.com/pypa/auditwheel/issues/321), [#362](https://github.com/pypa/auditwheel/pull/362))

## 5.1.0

Released Jan. 03, 2022

### User-facing changes
- [BUGFIX] libc version failed to be detected on CentOS8 based docker image ([#352](https://github.com/pypa/auditwheel/issues/352), [#353](https://github.com/pypa/auditwheel/pull/353))
- [FEATURE] Add support for `SOURCE_DATE_EPOCH` ([#346](https://github.com/pypa/auditwheel/issues/346), [#348](https://github.com/pypa/auditwheel/pull/348))
- [FEATURE] Add `manylinux_2_28` & `manylinux_2_31` policies ([#356](https://github.com/pypa/auditwheel/pull/356))
- [DOC] Reflect dependency on patchelf in README ([#355](https://github.com/pypa/auditwheel/pull/355))

### Housekeeping
- Fix setuptools warnings seen during builds (deprecation notices) ([#337](https://github.com/pypa/auditwheel/pull/337))
- Fix SDist includes files it shouldn't include ([#338](https://github.com/pypa/auditwheel/pull/338))
- Add `build` & `test-dist` nox sessions ([#336](https://github.com/pypa/auditwheel/pull/336))
- Add musllinux integration tests ([#317](https://github.com/pypa/auditwheel/pull/317))
- Rename the default branch from master to main ([#342](https://github.com/pypa/auditwheel/pull/342))
- Clean before build in test_manylinux ([#347](https://github.com/pypa/auditwheel/pull/347))
- Test with python 3.10 ([#345](https://github.com/pypa/auditwheel/pull/345))
- Move from `pbr` to `setuptools_scm`  ([#358](https://github.com/pypa/auditwheel/pull/358))
- Add nox `develop` session  ([#359](https://github.com/pypa/auditwheel/pull/359))

## 5.0.0

Released Sep. 18, 2021

### User-facing changes
- [BUGFIX] Remove undeclared dependency on pkg_resources ([#307](https://github.com/pypa/auditwheel/pull/307))
- [BUGFIX] Don't installs self in tox deps ([#319](https://github.com/pypa/auditwheel/pull/319))
- [FEATURE] Add support for musllinux ([#305](https://github.com/pypa/auditwheel/issues/305), [#311](https://github.com/pypa/auditwheel/pull/311), [#315](https://github.com/pypa/auditwheel/pull/315))
- [FEATURE] Replace `unzip` usage with Python's `zipfile` ([#258](https://github.com/pypa/auditwheel/issues/258), [#324](https://github.com/pypa/auditwheel/pull/324))
- [FEATURE] `libz.so.1` is now whitelisted (with some symbols blacklisted) ([#152](https://github.com/pypa/auditwheel/issues/152), [#161](https://github.com/pypa/auditwheel/issues/161), [#334](https://github.com/pypa/auditwheel/pull/334))

### Housekeeping
- Use python slim images to run tests ([#308](https://github.com/pypa/auditwheel/pull/308))
- Manylinux2014 now uses devtoolset-10 ([#316](https://github.com/pypa/auditwheel/pull/316))
- Use pre-commit to lint the code base ([#331](https://github.com/pypa/auditwheel/pull/331))
  - Run pyupgrade --py36-plus ([#325](https://github.com/pypa/auditwheel/pull/325))
  - Run isort --py 36 --profile black ([#328](https://github.com/pypa/auditwheel/pull/328))
  - Run black ([#329](https://github.com/pypa/auditwheel/pull/329))
- Move mypy config to pyproject.toml ([#326](https://github.com/pypa/auditwheel/pull/326))
- Move to an `src` layout ([#332](https://github.com/pypa/auditwheel/pull/332))

## 4.0.0

Released May. 5, 2021

- No changes since 4.0.0.0b1.

## 4.0.0.0b1

Released Apr. 3, 2021

### User-facing changes
- [BUGFIX] Patch RPATHs of non-Python extension dependencies ([#136](https://github.com/pypa/auditwheel/issues/136), [#298](https://github.com/pypa/auditwheel/pull/298))
- [BUGFIX] Ensure policies in `policy.json` are compliant with PEP600 ([#287](https://github.com/pypa/auditwheel/pull/287))
  - This removes 2 non existing symbols from manylinux1 i686 policy and removes ncurses librairies from manylinux1 whitelist.
- [FEATURE] Use PEP600 policy names ([#288](https://github.com/pypa/auditwheel/pull/288), [#297](https://github.com/pypa/auditwheel/pull/297))
  - The platform tag passed to `auditwheel repair` `--plat` argument can use either the PEP600 tag or the legacy tag. The repaired wheel will get both platform tags.
  - Inform about aliases in `auditwheel repair --help`
- [FEATURE] Always repair as a single wheel ([#289](https://github.com/pypa/auditwheel/pull/289))
  - Add argument `--only-plat` to `auditwheel repair` for those who were keeping only the lowest priority tag wheel (i.e. the one requested by `--plat` argument).
- [FEATURE] Add manylinux_2_27 policy ([#299](https://github.com/pypa/auditwheel/issues/299), [#300](https://github.com/pypa/auditwheel/pull/300))
- [FEATURE] Add libexpat.so.1 to whitelisted libraries starting with manylinux2010 ([#152](https://github.com/pypa/auditwheel/issues/152), [#301](https://github.com/pypa/auditwheel/pull/301))

### Housekeeping
- Add manylinux_2_24 tests ([#266](https://github.com/pypa/auditwheel/pull/266))
- Use GitHub Actions for x86_64 tests ([#282](https://github.com/pypa/auditwheel/pull/282), [#294](https://github.com/pypa/auditwheel/pull/294))
- Rework auditwheel show checks in test_manylinux.py  ([#295](https://github.com/pypa/auditwheel/pull/295))
- Fix warning issued when testing tests/unit/test_policy.py ([#296](https://github.com/pypa/auditwheel/pull/296))

## 3.3.1

Released Dec. 24, 2020

### User-facing changes
- [FEATURE] Vendor `wheel` to improve user experience ([#275](https://github.com/pypa/auditwheel/pull/275))

### Housekeeping
- Fix twine check warning
- Modernize Python syntax using `pyupgrade --py36-plus` ([#278](https://github.com/pypa/auditwheel/pull/278))
- Remove usage of `wheel` imported helpers for python 2/3 compatibility ([#276](https://github.com/pypa/auditwheel/pull/276))
- Bump `wheel` to 0.36.2 ([#273](https://github.com/pypa/auditwheel/pull/273))

## 3.3.0

Released Dec. 6, 2020

### User-facing changes
- [FEATURE] Add `--strip` option to repair ([#255](https://github.com/pypa/auditwheel/pull/255))
- [FEATURE] Add manylinux_2_24 policy ([#264](https://github.com/pypa/auditwheel/pull/264))
- [FEATURE] Add python 3.9 support ([#265](https://github.com/pypa/auditwheel/pull/265))
- [FEATURE] Drop python 3.5 support ([#261](https://github.com/pypa/auditwheel/pull/261))

### Housekeeping
- The PyPA has adopted the PSF code of conduct ([#256](https://github.com/pypa/auditwheel/pull/256))
- Remove unused `find_package_dirs` function ([#267](https://github.com/pypa/auditwheel/pull/267))
- Bump `wheel` to 0.36.1 ([#269](https://github.com/pypa/auditwheel/pull/269))

## 3.2.0

Released Jul. 1, 2020

### User-facing changes
- [FEATURE] Ensure that system-copied libraries are writable before running patchelf
  ([#237](https://github.com/pypa/auditwheel/pull/237))
- [FEATURE] Preserve RPATH in extension modules ([#245](https://github.com/pypa/auditwheel/pull/245))

## 3.1.1

Released Apr. 25, 2020

### User-facing changes
- [BUGFIX] Always exclude ELF dynamic linker/loader from analysis ([#213](https://github.com/pypa/auditwheel/pull/213))
  - Fixes "auditwheel repair marked internal so files as shared library dependencies ([#212](https://github.com/pypa/auditwheel/issues/212))"
- [BUGFIX] Correctly detect non-platform wheels ([#224](https://github.com/pypa/auditwheel/pull/224))
  - Fixes "Auditwheel addtag returns stack trace when given a none-any wheel ([#218](https://github.com/pypa/auditwheel/issues/218))"
- [BUGFIX] Fix obsolete wheel usage in addtag ([#226](https://github.com/pypa/auditwheel/pull/226))

### Housekeeping
- Upgrade `wheel` to 0.34.2 ([#235](https://github.com/pypa/auditwheel/pull/235))

## 3.1.0

Released Jan. 29, 2020

### User-facing changes
- [FEATURE] Put libraries in `$WHEELNAME.libs` to avoid vendoring multiple copies
  of the same library ([#90](https://github.com/pypa/auditwheel/pull/90))

### Housekeeping
- Upgrade `wheel` to 0.34  ([#223](https://github.com/pypa/auditwheel/pull/223))

## 3.0.0

Released Jan. 11, 2020

- No user facing changes since 3.0.0.0rc1.

## 3.0.0.0rc1

Released Nov. 7, 2019

### User-facing changes
- [FEATURE] manylinux2014 policy ([#192](https://github.com/pypa/auditwheel/pull/192), [#202](https://github.com/pypa/auditwheel/pull/202))
- [FEATURE] Update machine detection ([#201](https://github.com/pypa/auditwheel/pull/201))
- [FEATURE] Advertise python 3.8 support and run python 3.8 in CI ([#203](https://github.com/pypa/auditwheel/pull/203))

### Housekeeping
- Run manylinux tests using current python version ([#199](https://github.com/pypa/auditwheel/pull/199))

## 2.1.1

Released Oct. 08, 2019

### User-facing changes

- [BUGFIX] Add missing symbols for manylinux2010_i686 policy ([#141](https://github.com/pypa/auditwheel/pull/141), [#194](https://github.com/pypa/auditwheel/pull/194))
- [BUGFIX] Fix --version for python 3.10 ([#189](https://github.com/pypa/auditwheel/pull/189))

### Housekeeping

- Simplify policy unit test ([#188](https://github.com/pypa/auditwheel/pull/188))

## 2.1

Released Jul. 28, 2019

- Instead of outputting only the first shared library found in `purelib`,
  include a list of all offending files ([#143](https://github.com/pypa/auditwheel/pull/143))
- Better policy detection ([#150](https://github.com/pypa/auditwheel/pull/150))
- Use `AUDITWHEEL_PLAT` environment variable as a default option to --plat
  ([#151](https://github.com/pypa/auditwheel/pull/150))
- Workaround for `patchelf` bug not setting `DT_RUNPATH` correctly
  ([#173](https://github.com/pypa/auditwheel/pull/173))
- Remove `libcrypt.so.1` from library whitelist
  ([#182](https://github.com/pypa/auditwheel/pull/182))

## 2.0

Released Jan. 23, 2019

- After approximately 2 months of testing, no new regressions were detected in
  the 2.0 release candidate.
- Note that this release contains the implementation of [PEP
  571](https://www.python.org/dev/peps/pep-0571/), e.g. manylinux2010 support.

## 2.0rc1

Released Nov. 18, 2018

### User-facing changes

- [FEATURE] manylinux2010 policy support
  ([#92](https://github.com/pypa/auditwheel/pull/92),
  [#130](https://github.com/pypa/auditwheel/pull/130))
    - Closes the auditwheel portion of "manylinux2010 rollout" ([pypa/manylinux#179](https://github.com/pypa/manylinux/issues/179))
- [FEATURE] Drop Python 3.4 support and add Python 3.7 support
  ([#127](https://github.com/pypa/auditwheel/pull/127))

### Housekeeping

- Replace print statements with logger.
  ([#113](https://github.com/pypa/auditwheel/pull/113))
    - Closes [#109](https://github.com/pypa/auditwheel/issues/109)
- Many small code cleanup PRs:
    - Update Python versions in README and setup.cfg ([#123](https://github.com/pypa/auditwheel/pull/123))
    - Remove unneeded parentheses ([#122](https://github.com/pypa/auditwheel/pull/122))
    - Use a Pythonic context manager ([#118](https://github.com/pypa/auditwheel/pull/118))
    - Remove unused variables and imports ([#121](https://github.com/pypa/auditwheel/pull/121), [#117](https://github.com/pypa/auditwheel/pull/117))
    - Use Python 3 class syntax ([#119](https://github.com/pypa/auditwheel/pull/119))
    - Fix log.warn deprecation warning ([#120](https://github.com/pypa/auditwheel/pull/120))
- Fix Travis flakiness by disabling caches and remove broken auto-deployments
  ([#128](https://github.com/pypa/auditwheel/pull/128))

## 1.10

Released Nov. 17, 2018

- After three weeks of testing, no bugs were reported in 1.10rc1.

## 1.10rc1

Released Oct. 27, 2018

### User-facing changes

- [BUGFIX] Pin wheel to 0.31.1 to avoid the API break in the 0.32.0 release
  ([#106](https://github.com/pypa/auditwheel/pull/106))
   - Temporary fix for "auditwheel does not work with wheel>=0.32.0" ([#102](https://github.com/pypa/auditwheel/issues/102))
- [BUGFIX] Properly support non-extension wheels that contain binary dependencies ([#110](https://github.com/pypa/auditwheel/pull/110))
   - Fixes "Regression in tests from merging [#95](https://github.com/pypa/auditwheel/pull/95)" ("show" after "repair" no longer identifies the platform correctly) ([#107](https://github.com/pypa/auditwheel/issues/107))
   - Closes "Audit for binary files inside pure wheels" ([#32](https://github.com/pypa/auditwheel/issues/32))
   - Closes "Ensure that pure wheels are supported by 'repair'" ([#47](https://github.com/pypa/auditwheel/issues/47))
- [FEATURE] Support more platforms and Python implementations
  ([#98](https://github.com/pypa/auditwheel/pull/98))

### Housekeeping

- Add PyPI badge to the README
  ([#97](https://github.com/pypa/auditwheel/pull/97))
- Fix CD, hopefully ([#99](https://github.com/pypa/auditwheel/pull/99))
- Ensure Travis fails when the tests fail
  ([#106](https://github.com/pypa/auditwheel/pull/106))
- Remove the dot from `py.test` -> `pytest`
  ([#112](https://github.com/pypa/auditwheel/pull/112))

## 1.9

Released Jul. 3, 2018

### User-facing changes

- [BUGFIX] Skip pure wheels that don't need a platform added
  ([#71](https://github.com/pypa/auditwheel/pull/71))
    - Fixes "auditwheel repair should not fail on pure Python wheels" ([#47](https://github.com/pypa/auditwheel/issues/47))
- [FEATURE] Process non-Python binary executables (#95)
- [FEATURE] Add support for compiled cffi pypy extensions
  ([#94](https://github.com/pypa/auditwheel/pull/94))
    - Fixes "Undefined name 'src_name' in auditwheel/repair.py" ([#91](https://github.com/pypa/auditwheel/issues/91))
    - Closes "Support repairing cffi PyPy extensions" ([#93](https://github.com/pypa/auditwheel/issues/93))

### Housekeeping

- Remove unused `-f`/`--force` option for `main_repair.py`
  ([#96](https://github.com/pypa/auditwheel/pull/96))

## 1.8

Released Dec. 28, 2017

### User-facing changes

- [BUGFIX] Fix recursive `get_req_external`
  ([#84](https://github.com/pypa/auditwheel/pull/84))
- [BUGFIX] Add libresolv to the whitelisted libraries
  ([#81](https://github.com/pypa/auditwheel/pull/81))
    - Fixes "Whitelist libresolv" ([#80](https://github.com/pypa/auditwheel/issues/80))

### Housekeeping

- Typo fix in `auditwheel show`
  ([#83](https://github.com/pypa/auditwheel/pull/83))
- Make failing Travis wheelhouse test optional
  ([#87](https://github.com/pypa/auditwheel/pull/87))

## 1.7

Released May 26, 2017

### User-facing changes

- [BUGFIX] Fix symbol version checks for symbols that do not follow the format
  "NAME_X.X.X" ([#73](https://github.com/pypa/auditwheel/pull/73))
    - Fixes "ValueError in versioned symbols" ([#72](https://github.com/pypa/auditwheel/issues/72))

### Housekeeping

- Code simplication ([#74](https://github.com/pypa/auditwheel/pull/74))

## 1.6.1

Released May 2, 2017

## 1.6

Released May 24, 2017

- Bad release. Accidentally a duplicate of 1.4. See [#68
  (comment)](https://github.com/pypa/auditwheel/issues/68#issuecomment-298735698)

## 1.5

Released Oct. 23, 2016

## 1.4

Released May 25, 2016

## 1.3

Released Apr. 3, 2016

## 1.2

Released Mar. 23, 2016

## 1.1

Released Jan. 30, 2016

## 1.0

Released Jan. 20, 2016
