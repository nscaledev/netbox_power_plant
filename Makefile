sources = netbox_power_plant

.PHONY: test test-fast test-contract test-full unittest format lint pre-commit clean

test: test-contract

test-fast:
	./devrun/test.sh fast

test-contract:
	./devrun/test.sh contract

test-full:
	./devrun/test.sh full

unittest: test-full

format:
	black $(sources)

lint:
	flake8 $(sources)

pre-commit:
	pre-commit run --all-files

clean:
	rm -rf *.egg-info
	rm -rf .tox dist site build
