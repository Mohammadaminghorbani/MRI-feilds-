# Makefile
SHELL := /bin/bash

.PHONY: help
help:
	@echo "Commands:"
	@echo "venv    : creates development environment."
	@echo "style   : runs style formatting."
	@echo "clean   : cleans all unnecessary files."
	@echo "test    : run non-training tests."

.PHONY: install
install:
	python3 -m pip install -e . --no-cache-dir
	python3 -m pip install --pre --extra-index https://pypi.anaconda.org/scipy-wheels-nightly/simple scikit-learn

# Environment
.ONESHELL:
venv:
	virtualenv .venv --python=python3.10
	source .venv/bin/activate
	# python3 -m pip install numpy==1.22.1
	python3 -m pip install -e ".[dev]" --no-cache-dir
	python3 -m pip install --pre --extra-index https://pypi.anaconda.org/scipy-wheels-nightly/simple scikit-learn
	pre-commit install
	pre-commit autoupdate

# Build webapp
.ONESHELL:
build-app:
	python3 -m pip install pyoxidizer
	pyoxidizer build install
	mkdir -p js/app/python
	mv -f build/dist/* js/app/python/
	rm -r build/

.ONESHELL:
build-node:
	yarn install
	yarn build

.ONESHELL:
clean-before-app:
	cd js/app
	rm -r app/ dist/ python/ yarn.lock node_modules/
	cd ../../
	deactivate
	rm -r .venv
	virtualenv .venv --python=python3.10
	source .venv/bin/activate

# Styling
.PHONY: style
style:
	black .
	flake8
	isort .

# Cleaning
.PHONY: clean
clean: style
	find . -type f -name "*.DS_Store" -ls -delete
	find . | grep -E "(__pycache__|\.pyc|\.pyo)" | xargs rm -rf
	find . | grep -E ".pytest_cache" | xargs rm -rf
	find . | grep -E ".ipynb_checkpoints" | xargs rm -rf
	rm -f .coverage

# Publishing to PyPI
.ONESHELL:
prepare-to-publish:
	python3 -m pip install build twine
	python3 -m build
	twine check dist/*
	twine upload -r testpypi dist/*

publish:
	twine upload dist/*

# Test
.PHONY: test
test:
	# great_expectations checkpoint run projects
	# great_expectations checkpoint run tags
	pytest
