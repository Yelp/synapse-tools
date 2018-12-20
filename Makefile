DATE := $(shell date +'%Y-%m-%d')
SYNAPSETOOLSVERSION := $(shell sed 's/.*(\(.*\)).*/\1/;q' src/debian/changelog)

.PHONY: bintray_%
bintray_%: bintray.json.in src/debian/changelog
	sed -e 's/@DATE@/$(DATE)/g' \
	    -e 's/@SYNAPSETOOLSVERSION@/$(SYNAPSETOOLSVERSION)/g' \
	    -e 's/@DISTRIBUTION@/$*/g' \
            bintray.json.in > bintray.json

.PHONY: itest_%
itest_%: package_% bintray_%
	rm -rf dockerfiles/itest/itest_$*
	cp -a dockerfiles/itest/itest dockerfiles/itest/itest_$*
	cp dockerfiles/itest/itest/Dockerfile.$* dockerfiles/itest/itest_$*/Dockerfile
	tox -e itest_$*

.PHONY: package_%
package_%:
	[ -d dist ] || mkdir dist
	tox -e package_$*

.PHONY: mypy
mypy:
	cd src && tox -e mypy

.PHONY: clean
clean:
	tox -e fix_permissions
	git clean -Xfd
