# Change Log

## [v0.13.21](https://github.com/Yelp/synapse-tools/tree/v0.13.21) (2018-06-14)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.20...v0.13.21)

**Merged pull requests:**

- Clean up old shutting-down nginx if we need to reload again. [\#56](https://github.com/Yelp/synapse-tools/pull/56) ([EvanKrall](https://github.com/EvanKrall))

## [v0.13.20](https://github.com/Yelp/synapse-tools/tree/v0.13.20) (2018-05-16)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.19...v0.13.20)

**Merged pull requests:**

- Pass a 0 as source for unidentifiable services [\#55](https://github.com/Yelp/synapse-tools/pull/55) ([avadhutp](https://github.com/avadhutp))

## [v0.13.19](https://github.com/Yelp/synapse-tools/tree/v0.13.19) (2018-04-16)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.18...v0.13.19)

**Merged pull requests:**

- Allow plugins to reorder their directives [\#53](https://github.com/Yelp/synapse-tools/pull/53) ([avadhutp](https://github.com/avadhutp))

## [v0.13.18](https://github.com/Yelp/synapse-tools/tree/v0.13.18) (2018-03-22)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.16...v0.13.18)

**Merged pull requests:**

- Enabled the source_required plugin [\#52](https://github.com/Yelp/synapse-tools/pull/52) ([avadhutp](https://github.com/avadhutp))

## [v0.13.16](https://github.com/Yelp/synapse-tools/tree/v0.13.16) (2018-02-27)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.15...v0.13.16)

**Merged pull requests:**

- Fix simultaneous builds on a single Jenkins box [\#49](https://github.com/Yelp/synapse-tools/pull/49) ([avadhutp](https://github.com/avadhutp))

## [v0.13.15](https://github.com/Yelp/synapse-tools/tree/v0.13.15) (2018-02-16)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.14...v0.13.15)

**Merged pull requests:**

- Add backports.functools_lru_cache to requirements [\#48](https://github.com/Yelp/synapse-tools/pull/48) ([avadhutp](https://github.com/avadhutp))

## [v0.13.14](https://github.com/Yelp/synapse-tools/tree/v0.13.14) (2018-02-14)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.13...v0.13.14)

**Merged pull requests:**

- Update version everywhere [\#47](https://github.com/Yelp/synapse-tools/pull/47) ([avadhutp](https://github.com/avadhutp))

## [v0.13.13](https://github.com/Yelp/synapse-tools/tree/v0.13.13) (2018-02-13)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.13.12...v0.13.13)

**Merged pull requests:**

- Fix lucid builds [\#45](https://github.com/Yelp/synapse-tools/pull/46) ([avadhutp](https://github.com/avadhutp))

## [v0.13.12](https://github.com/Yelp/synapse-tools/tree/v0.13.12) (2018-02-13)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.11.4...v0.13.12)

**Merged pull requests:**

- Enable fault-injection via the use of X-Ctx-Tarpit headers [\#45](https://github.com/Yelp/synapse-tools/pull/45) ([avadhutp](https://github.com/avadhutp))

## [v0.11.4](https://github.com/Yelp/synapse-tools/tree/v0.11.4) (2017-01-10)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.11.3...v0.11.4)

**Merged pull requests:**

- Switch over to use /opt/venvs in preperation for the new version of dh-virtualenv [\#14](https://github.com/Yelp/synapse-tools/pull/14) ([solarkennedy](https://github.com/solarkennedy))

## [v0.11.3](https://github.com/Yelp/synapse-tools/tree/v0.11.3) (2016-12-20)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.11.2...v0.11.3)

**Merged pull requests:**

- Have haproxy-synapse expose unix sockets for each service [\#13](https://github.com/Yelp/synapse-tools/pull/13) ([jglukasik](https://github.com/jglukasik))

## [v0.11.2](https://github.com/Yelp/synapse-tools/tree/v0.11.2) (2016-12-07)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.11.1...v0.11.2)

**Merged pull requests:**

- made synapse-tools process the typ:loc labels [\#12](https://github.com/Yelp/synapse-tools/pull/12) ([mjksmith](https://github.com/mjksmith))

## [v0.11.1](https://github.com/Yelp/synapse-tools/tree/v0.11.1) (2016-12-06)
[Full Changelog](https://github.com/Yelp/synapse-tools/compare/v0.11.0...v0.11.1)

## [v0.11.0](https://github.com/Yelp/synapse-tools/tree/v0.11.0) (2016-12-03)
**Closed issues:**

- Build packages publicly [\#5](https://github.com/Yelp/synapse-tools/issues/5)

**Merged pull requests:**

- added backup backends to synapse [\#11](https://github.com/Yelp/synapse-tools/pull/11) ([mjksmith](https://github.com/mjksmith))
- Fixed make itest\_lucid and make itest\_trusty [\#10](https://github.com/Yelp/synapse-tools/pull/10) ([mjksmith](https://github.com/mjksmith))
- Make haproxy stats port configurable [\#9](https://github.com/Yelp/synapse-tools/pull/9) ([EvanKrall](https://github.com/EvanKrall))
- Pull all hard-coded values into configuration. [\#8](https://github.com/Yelp/synapse-tools/pull/8) ([EvanKrall](https://github.com/EvanKrall))
- When adding extra headers, delete those headers. [\#7](https://github.com/Yelp/synapse-tools/pull/7) ([bobtfish](https://github.com/bobtfish))
- Public package build [\#6](https://github.com/Yelp/synapse-tools/pull/6) ([EvanKrall](https://github.com/EvanKrall))
- Use c yaml bindings [\#4](https://github.com/Yelp/synapse-tools/pull/4) ([jolynch](https://github.com/jolynch))
- Added load balancing strategy option [\#2](https://github.com/Yelp/synapse-tools/pull/2) ([oholiab](https://github.com/oholiab))



\* *This Change Log was automatically generated by [github_changelog_generator](https://github.com/skywinder/Github-Changelog-Generator)*
