import requests_cache
from pygerrit.rest import GerritRestAPI
from networkx.readwrite import json_graph
import json
from requests.exceptions import HTTPError
import networkx as nx
from datetime import *
from dateutil.parser import parse
import glob
import os
from ago import human
from time import localtime, strftime
import jinja2
import argparse
import ConfigParser

def save_to_json(di_graph, output_filename='data.json', q='Unknown Query', max_elapsed=0, min_elapsed=0):
    data = json_graph.node_link_data(di_graph,
                                     attrs={'id': 'name', 'source': 'source', 'target': 'target', 'key': 'key'})
    data["query"] = q
    data["maxtime"] = max_elapsed
    data["mintime"] = min_elapsed
    data["date"] = datetime.now().isoformat()
    # clean up json
    del data["directed"]
    del data["graph"]
    del data["multigraph"]
    # save
    with open(output_filename, 'w') as outfile:
        json.dump(data, outfile)

def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)

class DebugLogger(object):
    def __init__(self, context):
        self.context = context

    def warning(self, msg, *args):
        print(self.context + ' Warning:' + msg % args)

    def error(self, msg, *args):
        print(self.context + ' Error:' + msg % args)


def generateHTML(template, output, **kwargs):
    # print("Starting {0}".format(output))
    undefined = jinja2.make_logging_undefined(DebugLogger(output))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(template), undefined=undefined)
    output_from_parsed_template = env.get_template('').render(kwargs)

    with open(output, "wb") as f:
        try:
            f.write(output_from_parsed_template.encode('utf8'))
        except Exception as exc:
            print(exc)
            print(output_from_parsed_template)

# 1200 hour cache of all requests (we skip cache for some and remove "open" changes
# http://requests-cache.readthedocs.io/en/latest/user_guide.html#installation
requests_cache.install_cache('cache_review_openstack_org', backend='sqlite', expire_after=60 * 60 * 24 * 50,
                             allowable_codes=(200, 404, 500))

try:


    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("files", metavar="FILE", nargs='+', help="Configuration Files")

    args = arg_parser.parse_args()
    config = ConfigParser.ConfigParser()
    # Preserve Case in keys
    config.optionxform = str
    for config_file in args.files:
        if not os.path.exists(config_file):
            raise ValueError('Failed to open/read "{file}"'.format(file=config_file))
        config.read(config_file)
except ImportError:
    args = None



gerrit_service = config.get('Header', 'gerrit')
    #'https://review.openstack.org'
human_gerrit_service = config.get('Header', 'human_gerrit')
# "https://review.openstack.org/#/q/"
rest = GerritRestAPI(url=gerrit_service)

queries = config.items("Queries")
for output_file, query in queries:
    #HACK to exclude [DEFAULT] items
    if not output_file.startswith('_'):
        print("Processing '{0}' to File '{1}.json' ".format(query,output_file))

        # Don't cache the gerrit search query
        with requests_cache.disabled():
            changes = rest.get("/changes/?q=" + query)

        G = nx.DiGraph()
        counter = 0

        maxtime = 0

        for change in changes:
            print("{0} - {1}".format(counter, change['id']))
            try:
                detail_query = "/changes/{0}/detail".format(change['id'])
                detail = rest.get(detail_query)

                # Remove open ones from cache
                if detail['status'] in ['NEW', 'OPEN', 'PENDING']:
                    requests_cache.core.get_cache().delete_url(gerrit_service + detail_query)

                nodes = {}
                # Sometimes name is missing so use username or email
                user_label = detail['owner'].get('name',
                                                 detail['owner'].get('username', detail['owner'].get('email', 'Unknown')))

                path = [user_label]
                visited = [user_label]
                times = [parse(detail['created'])]

                depth = 1
                for msg in detail['messages']:
                    if "Code-Review+2" in msg['message']:
                        # Avoid self loops and cycles
                        if msg['author']['name'] not in visited:
                            # , " W" if "Workflow+1" in msg['message'] else ""))
                            path.append(u"{0}: {1}".format(depth, msg['author']['name']))
                            visited.append(msg['author']['name'])
                            times.append(parse(msg['date']))
                            depth += 1

                path.append(detail['status'])
                times.append(parse(detail['updated']))

                if depth > 1:
                    for a, b, t1, t2 in zip(path[:-1], path[1:], times[:-1], times[1:]):
                        elapsed = t2 - t1
                        param = 'avgtime'
                        elapsed_seconds = elapsed.total_seconds()

                        if G.has_edge(a, b):
                            # running average
                            G[a][b]['avgtime'] = (G[a][b]['avgtime'] * G[a][b]['value'] + elapsed_seconds) / (
                            G[a][b]['value'] + 1)
                            # count
                            G[a][b]['value'] += 1
                            # changes
                            G[a][b]['changes'] = G[a][b]['changes'] + " OR " + change['id']
                        else:
                            # running average, count, first change
                            G.add_edge(a, b, {'value': 1, 'avgtime': elapsed_seconds, 'changes': change['id']})

                            # if 'changes' in G[a]:
                            #     G[a]['changes'] = G[a]['changes'] + " OR " + change['id']
                            # else:
                            #     G[a]['changes'] = change['id']
                            #
                            # if 'changes' in G[b]:
                            #     G[b]['changes'] = G[b]['changes'] + " OR " + change['id']
                            # else:
                            #     G[b]['changes'] = change['id']

                counter += 1
                # Enable to save a debugging png of the graph to file
                # nx.draw(G, hold=False)
                # plt.savefig("{0}_path.png".format(i))
                # Clear
                # plt.clf()

            except HTTPError as err:
                print("Error: {0}".format(err))
                pass

        # Begin merging to "others"
        # How many to *try* and keep... In the event of a tie we might have more
        keep_top = 15

        # Get an ordered dic of all left hand nodes (with no inputs, in_degree==0)
        parents = {a: b for a, b in G.in_degree().iteritems() if b == 0}.keys()
        parents_out_values = G.out_degree(parents, weight='value').values()

        # Find a value below which to merge.
        keep_value = 1 if len(parents_out_values) < keep_top else sorted(parents_out_values, reverse=True)[keep_top]

        # Loop through the "out" edges of all nodes
        for k in [a for a in parents if G.out_degree(a, weight='value') < keep_value]:
            for a, b in G.out_edges(k):
                value = G.edge[k][b]['value']
                if G.has_edge('Others', b):
                    G['Others'][b]['value'] = G['Others'][b]['value'] + value
                    G['Others'][b]['avgtime'] = (G['Others'][b]['avgtime'] + G['Others'][b]['avgtime']) / 2
                else:
                    G.add_edge('Others', b, value=value, avgtime=G.edge[k][b]['avgtime'])
            G.remove_node(k)

        # calc max time and min time (firsta and last from sorted)
        # TODO this lambda syntax won't work in python 3
        sorted_edges = sorted(G.edges(data=True), reverse=True, key=lambda (source, target, data): data['avgtime'])
        full_path = './html/json/' + output_file + '.json'
        save_to_json(G, full_path, human_gerrit_service + query,  sorted_edges[0][2]['avgtime'], sorted_edges[-1][2]['avgtime'])
        print("Done @ {0}, Wrote to: {1}".format(datetime.now(), full_path))

print("Rebuilding Index")
index_file='html/index.html'
files = []
for f in sorted(glob.glob("html/json/*.json")):
    o = {
    "name" : os.path.basename(f),
    "ago" : human(os.path.getmtime(f)),
    "size" : sizeof_fmt(os.stat(f).st_size)
    }
    files.append(o)
    #print f
    #print(human(os.path.getmtime(f)))
generateHTML('templates/_index.html', 'html/index.html', files=files,  now = strftime("%Y-%m-%d %H:%M:%S", localtime()))
print("Done @ {0}, Wrote to: {1}".format(datetime.now(), index_file))
# TODO Group small ones together as others
# TODO Add average time lag as additional data to edge
# TODO Colour code edges based on time
