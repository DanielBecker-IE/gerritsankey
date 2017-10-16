# gerritsankey
Generate Sankey Diagrams from Gerrit Queries 
Usage:
gerritSankey.py sankey.cfg

This will generate a index.html in the html directory with links to generated diagrams for the queries listed in the config file.

Please read the sankey.cfg file carefully before running. NOTE: The Gerrit Server may block you if you hit it too hard. Run a smaller set of query first and then expand. This will populate the cache.

Currently MERGED changes are cached for a long time delete the generated sqllite file to clear.

This has only been tested against Python 2.7.10 (has a known python 3 syntax TODO) and against the Openstack Gerrit server.

