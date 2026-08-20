#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

BRANCH="${INDUSTRY_BRANCH:-indy-calc}"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Refusing to update because the VM checkout has local changes." >&2
  echo "Keep production configuration in ignored files such as backend/.env.production." >&2
  git status --short >&2
  exit 1
fi

current_branch="$(git branch --show-current)"
if [[ "${current_branch}" != "${BRANCH}" ]]; then
  echo "Expected branch ${BRANCH}, but the VM checkout is on ${current_branch:-detached HEAD}." >&2
  exit 1
fi

git fetch origin "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

bash "${SCRIPT_DIR}/deploy.sh"
