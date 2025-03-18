#!/bin/sh
# Usage: ci/mypy-for-changes.sh
#
# This script is used to run mypy only on the changes in the current branch
# compared to the master branch. It is useful to run this script afer making
# changes to the code to ensure that the changes are valid and do not introduce
# any type errors.

if [ ! -x .git/reviewdog ]; then
    echo "reviewdog not found in .git directory. Downloading..."
    mkdir -p .git
    API_URL="https://api.github.com/repos/reviewdog/reviewdog/releases/latest"
    URL=$(curl -s $API_URL | grep "browser_download_url.*Linux_x86_64.tar"| cut -d'"' -f4)
    curl --location "$URL" | tar xz -f - -C .git reviewdog
    if [ ! -x .git/reviewdog ]; then
        echo "Failed to download reviewdog"
        exit 1
    fi
fi

# Get the current branch name
CURRENT_BRANCH=$(git branch --show-current)
if [ -z "$CURRENT_BRANCH" ]; then
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
fi
if [ -z "$CURRENT_BRANCH" ]; then
    echo "Failed to determine current branch"
    exit 1
fi

# Get the master branch name
MASTER_BRANCH=master
if [ "$CURRENT_BRANCH" = "$MASTER_BRANCH" ]; then
    MASTER_BRANCH=origin/$MASTER_BRANCH
fi

if [ -n "$GITHUB_STEP_SUMMARY" ]; then
    exec >"$GITHUB_STEP_SUMMARY" 2>&1
    echo "### mypy"
    # Add an extra option to reviewdog to report the results as a GitHub check:
    ARGS="-level=info -fail-on-error=false"
    if [ -n "$REVIEWDOG_GITHUB_API_TOKEN" ]; then
        # shellcheck disable=SC2086
        set -- $ARGS -reporter=github-check "$@"
    else
        echo "REVIEWDOG_GITHUB_API_TOKEN is not set."
        echo "The GitHub check will not be created, tying to use GitHub annotations instead."
        # shellcheck disable=SC2086
        set -- $ARGS -reporter=github-annotations -filter-mode=nofilter "$@"
    fi
else
    # Only needed for local testing: compare the current branch to the master branch
    # shellcheck disable=SC2089
    set -- "-diff=git diff $MASTER_BRANCH" "$@"
fi


DOG=$(.git/reviewdog -version)
MYPY=$(mypy --version)
echo "Using Reviewdog $DOG and $MYPY for changes to $MASTER_BRANCH" >&2

mypy --config=ci/mypy-for-changes.ini --show-column-numbers --no-pretty \
    2>&1 >.git/mypy.log  |sed '/SyntaxWarning: invalid escape sequence/,+1d'

if [ -n "$GITHUB_STEP_SUMMARY" ]; then
    echo "### mypy output"
    cat .git/mypy.log
fi

# If GITHUB_STEP_SUMMARY is set, append the mypy output to the file. This is
# useful when running this script in a GitHub action. In that case, the output
# will be shown in the GitHub action summary:
# https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#adding-a-job-summary


# shellcheck disable=SC2086,SC2090
.git/reviewdog \
    -name="mypy" \
    -efm="%f:%l:%c: %t%*[^:]: %m" \
    -efm="%f:%l: %t%*[^:]: %m" \
    -efm="%f: %t%*[^:]: %m" \
    --filter-mode=added \
    "$@" \
    <.git/mypy.log
