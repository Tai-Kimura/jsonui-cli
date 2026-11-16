"""The release gate accepts CI's cached apt route and still detects removed SVG dependencies."""
import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ci_image_deps', REPO / 'dev-guide/release/check_ci_image_deps.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def workflow(steps):
    return {'jobs': {'python-suite': {'steps': steps}}}


def test_the_current_workflow_installs_both_dependencies():
    assert check.missing(yaml.safe_load((REPO / '.github/workflows/ci.yml').read_text())) == []


def test_direct_apt_and_pip_remain_supported():
    assert check.missing(workflow([{'run': 'sudo apt-get install -y -qq librsvg2-bin\npip install cairosvg'}])) == []


def cached_steps():
    return [{'id': 'aptlist', 'run': 'pkgs="librsvg2-bin chromium-libraries"\necho "packages=$pkgs" >> "$GITHUB_OUTPUT"'},
            {'run': 'bash .github/scripts/apt_install_cached.sh "$HOME/apt-debs" ${{ steps.aptlist.outputs.packages }}\npython -m pip install cairosvg'}]


def test_cached_apt_must_consume_the_published_package_list():
    assert check.missing(workflow(cached_steps())) == []
    steps = cached_steps()
    steps[1]['run'] = steps[1]['run'].replace('steps.aptlist.', 'steps.other.')
    assert check.missing(workflow(steps)) == ['librsvg2-bin']


@pytest.mark.parametrize('dependency', ['librsvg2-bin', 'cairosvg'])
def test_removing_a_dependency_is_detected(dependency):
    steps = cached_steps()
    for step in steps:
        step['run'] = step['run'].replace(dependency, 'different-package')
    assert check.missing(workflow(steps)) == [dependency]


def test_comments_and_other_jobs_do_not_supply_missing_install_steps():
    data = workflow([{'run': '# apt-get install librsvg2-bin\n# pip install cairosvg'}])
    data['jobs']['other'] = {'steps': [{'run': 'apt-get install librsvg2-bin\npip install cairosvg'}]}
    assert check.missing(data) == ['librsvg2-bin', 'cairosvg']
