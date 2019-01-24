# auditwheel changelog

## HEAD

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
