import os
import subprocess

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

run('git checkout feature/tui-dashboard')
run('git cherry-pick main')
run('git checkout main')
run('git reset --hard HEAD~1')
run('git checkout feature/tui-dashboard')
run('git push origin feature/tui-dashboard')
