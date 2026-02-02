

# Prerequisitories

Install the package manager uv by executing this command in the Terminal. Other installation methods are documented in uv documentation.

## Create a virtual environment

Using uv and python 3.10 or 3.11:

```
uv venv --python 3.11
```

## Activate the virtual env:

```
source .venv/bin/activate
```

## Install rasa

```
uv pip install rasa
```

## To train the bot

```
rasa train
```

## To run the bot

```
rasa run
```

# Project structure

data/nlu/ → ce que l’utilisateur dit

data/stories/ → parcours conversationnels

data/rules/ → comportements fixes

data/lookups/ → données métier

actions/api/