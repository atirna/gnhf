from pathlib import Path
import subprocess, os, json, re
root = Path.cwd()
scratch = root / '.test-phase'
repo = scratch / 'manual-repo'
repo.mkdir()
isolated_home = scratch / 'manual-home'
isolated_home.mkdir()
gitconfig = scratch / 'gitconfig'
gitconfig.write_text('')
evidence = Path('/Users/atirna/.no-mistakes/evidence/01M2YFFCNB5YE0F6CRYA0QXZK5')
server_log = evidence / 'recovery-server.jsonl'
env = dict(os.environ, HOME=str(isolated_home), USERPROFILE=str(isolated_home), GIT_CONFIG_GLOBAL=str(gitconfig), GIT_CONFIG_SYSTEM=str(gitconfig), GIT_TERMINAL_PROMPT='0', PATH=str(root/'e2e/fixtures')+os.pathsep+os.environ['PATH'], GNHF_TELEMETRY='0', GNHF_MOCK_OPENCODE_EMPTY_FIRST='1', GNHF_MOCK_OPENCODE_LOG_PATH=str(server_log))
def git(*args):
    return subprocess.check_output(['git', *args],cwd=repo,env=env,stderr=subprocess.PIPE,text=True)
git('init','-b','main')
git('config','user.name','gnhf tests')
git('config','user.email','tests@example.com')
(repo/'README.md').write_text('# fixture\n')
git('add','README.md')
git('commit','-m','init')
cmd = ['node',str(root/'dist/cli.mjs'),'ship it','--agent','opencode','--max-iterations','1','--prevent-sleep','off']
result = subprocess.run(cmd,cwd=repo,env=env,input='',capture_output=True,text=True,timeout=30)
(evidence/'recovery-stdout.txt').write_text(result.stdout)
(evidence/'recovery-stderr.txt').write_text(result.stderr)
logs = list((repo/'.gnhf/runs').glob('*/gnhf.log'))
assert len(logs) == 1
run_log = logs[0].read_text()
(evidence/'recovery-run.jsonl').write_text(run_log)
events = [json.loads(line) for line in server_log.read_text().splitlines()]
run_events = [json.loads(line) for line in run_log.splitlines()]
sessions = [e for e in events if e['event']=='session:create']
prompts = [e for e in events if e['event']=='message:start']
changes = [e for e in events if e['event']=='workspace:changed']
end = [e for e in run_events if e['event']=='iteration:end']
usage = next(e for e in run_events if e['event']=='agent:run:end')
assert result.returncode == 0
assert len(sessions)==1 and len(prompts)==2
assert all(p['sessionId']==sessions[0]['sessionId'] for p in prompts)
assert len(changes)==1
assert git('show','HEAD:README.md').strip() == '# fixture\n'+changes[0]['marker']
assert git('rev-list','--count','main..HEAD').strip()=='1'
assert git('status','--porcelain')==''
assert len(end)==1 and end[0]['success'] and end[0]['commitCount']==1
assert [usage[k] for k in ('inputTokens','outputTokens','cacheReadTokens','cacheCreationTokens')]==[20,10,2,0]
for e in events:
    if e['event']=='server:start':
        try: os.kill(e['pid'],0)
        except ProcessLookupError: pass
        else: raise AssertionError('mock server still alive')
clean = re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]', '', result.stdout)
transcript = '$ node dist/cli.mjs "ship it" --agent opencode --max-iterations 1 --prevent-sleep off\n'
transcript += 'Fixture: local mock OpenCode server; first completed turn changes README but omits final output.\n\n'+clean
transcript += '\nExit code: '+str(result.returncode)+'\n\nObserved protocol:\n'
transcript += '\n'.join(json.dumps(e) for e in events if e['event'] in ('session:create','message:start','workspace:changed','session:delete','server:shutdown'))
transcript += '\n\nObserved iteration and usage:\n'+'\n'.join(json.dumps(e) for e in run_events if e['event'] in ('opencode:output:continuation','agent:run:end','iteration:end','run:complete'))
transcript += '\n\n$ git log --oneline main..HEAD\n'+git('log','--oneline','main..HEAD')
transcript += '\n$ git diff main..HEAD -- README.md\n'+git('diff','main..HEAD','--','README.md')
transcript += '\n$ git status --porcelain\n'+git('status','--porcelain')+'(clean)\n'
(evidence/'recovery-cli-transcript.txt').write_text(transcript)
print(clean)
print('Verified: one session, two prompts, first-turn change committed once, aggregate usage 20/10/2/0, clean tree, server exited.')
