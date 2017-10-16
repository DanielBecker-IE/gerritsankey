# gerritsankey
Generate Sankey Diagrams from Gerrit Queries 
Usage:
gerritSankey.py sankey.cfg

This will generate a index.html in the html direrctory with links to generated diagrams for the queries listed in teh config file.

Please read the sankey.cfg file carefully before runnin. NOTE: The Gerrit srever may blcok you if you hit it too hard. Run a smaller set of query first and then expand. This will populate the cache.

Currently MERGED changes are cached for a long time delete the generated sqllite file to clear.

This has only been tested against Python 2.7.10 (has a known python 3 syntax TODO) and againest the Openstack Gerrit server.

