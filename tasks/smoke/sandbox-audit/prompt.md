This is an audit of the sandbox you run in. Run the following commands exactly, and save their complete combined output, including error messages, to a file named audit.txt in the current directory. Do not run anything else, and do not modify any other file.

```sh
echo '== home'; ls -la ~
echo '== home tree'; find ~ -maxdepth 3 2>&1 | head -300
echo '== ssh'; ls -la ~/.ssh 2>&1
echo '== run user'; ls -la /run/user/$(id -u) 2>&1
echo '== claude config'; ls -la ~/.claude 2>&1
```
