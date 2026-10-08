.PHONY: install notebooks diagrams frontend dev deploy deploy-accounts cleanup destroy test

install:            ## Poetry (.venv at repo root) + frontend deps
	poetry install
	cd frontend && npm ci

notebooks:          ## Regenerate .ipynb from the .py (percent format) sources
	for f in workshop/0*/0*.py workshop/99_cleanup/99_cleanup.py; do poetry run jupytext --set-kernel python3 --to ipynb $$f; done

diagrams:           ## Regenerate draw.io diagrams + DPI-400 PNGs (needs draw.io desktop)
	poetry run python assets/diagrams/build_diagrams.py

frontend:           ## Build the portal
	cd frontend && npm run build

dev:                ## Run the portal locally (http://localhost:5173)
	poetry run python scripts/frontend_local_config.py && cd frontend && npm run dev

deploy:             ## Deploy foundation + portal to the current AWS account
	./scripts/deploy.sh

deploy-accounts:    ## make deploy-accounts PROFILES="team01 team02"
	./scripts/deploy_multi_account.sh $(PROFILES)

cleanup:            ## Delete AI resources created by the notebooks
	poetry run python workshop/99_cleanup/99_cleanup.py

destroy:            ## cleanup + cdk destroy
	./scripts/destroy.sh

test:               ## CDK unit tests
	cd infrastructure && poetry run pytest -q tests
