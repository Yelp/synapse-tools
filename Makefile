all: itest_trusty

itest_trusty: package_trusty bintray.json
	rm -rf dockerfiles/itest/itest_trusty
	cp -a dockerfiles/itest/itest dockerfiles/itest/itest_trusty
	cp dockerfiles/itest/itest/Dockerfile.trusty dockerfiles/itest/itest_trusty/Dockerfile
	tox -e itest_trusty

DATE := $(shell date +'%Y-%m-%d')
SYNAPSETOOLSVERSION := $(shell sed 's/.*(\(.*\)).*/\1/;q' src/debian/changelog)
bintray.json: bintray.json.in src/debian/changelog
	sed -e 's/@DATE@/$(DATE)/g' -e 's/@SYNAPSETOOLSVERSION@/$(SYNAPSETOOLSVERSION)/g' $< > $@

package_trusty:
	[ -d dist ] || mkdir dist
	tox -e package_trusty

# Note: itest_lucid will not build outside of Yelp - it depends on python2.7, which is not generally available for lucid anymore.
itest_lucid: package_lucid
	rm -rf dockerfiles/itest/itest_lucid
	cp -a dockerfiles/itest/itest dockerfiles/itest/itest_lucid
	cp dockerfiles/itest/itest/Dockerfile.lucid dockerfiles/itest/itest_lucid/Dockerfile
	tox -e itest_lucid

package_lucid:
	[ -d dist ] || mkdir dist
	tox -e package_lucid

clean:
	tox -e fix_permissions
	git clean -Xfd
