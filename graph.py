from itertools import islice
from operator import itemgetter
import math
import matplotlib.pyplot as plt
from xml.dom.minidom import parse
import xml.dom.minidom
import networkx as nx
import numpy as np
import logging


def get_k_shortest_paths(G, source, target, k, weight=None):
    """
    Method from https://networkx.github.io/documentation/stable/reference/algorithms/generated/networkx.algorithms.simple_paths.shortest_simple_paths.html#networkx.algorithms.simple_paths.shortest_simple_paths
    """
    return list(islice(nx.shortest_simple_paths(G, source, target, weight=weight), k))


def get_path_weight(graph, path, weight='length'):
    return np.sum([graph[path[i]][path[i+1]][weight] for i in range(len(path) - 1)])


class Path:

    def __init__(self, node_list, length):
        self.node_list = node_list
        self.length = length
        self.hops = len(node_list) - 1


def calculate_geographical_distance(latlong1, latlong2):
    R = 6373.0

    lat1 = math.radians(latlong1[0])
    lon1 = math.radians(latlong1[1])
    lat2 = math.radians(latlong2[0])
    lon2 = math.radians(latlong2[1])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    length = R * c
    return length


def read_sndlib_topology(file):
    graph = nx.Graph()

    with open('config/topologies/' + file) as file:
        tree = xml.dom.minidom.parse(file)
        document = tree.documentElement

        graph.graph["coordinatesType"] = document.getElementsByTagName("nodes")[0].getAttribute("coordinatesType")

        # Stores the "node" elements on the XML file on nodes
        nodes = document.getElementsByTagName("node")
        for node in nodes:
            x = node.getElementsByTagName("x")[0]
            y = node.getElementsByTagName("y")[0]
            graph.add_node(node.getAttribute("id"), pos=((float(x.childNodes[0].data), float(y.childNodes[0].data))))
        links = document.getElementsByTagName("link")
        for idx, link in enumerate(links):
            source = link.getElementsByTagName("source")[0]
            target = link.getElementsByTagName("target")[0]

            if graph.graph["coordinatesType"] == "geographical":
                length = np.around(calculate_geographical_distance(graph.nodes[source.childNodes[0].data]["pos"], graph.nodes[target.childNodes[0].data]["pos"]), 3)
            else:
                latlong1 = graph.nodes[source.childNodes[0].data]["pos"]
                latlong2 = graph.nodes[target.childNodes[0].data]["pos"]
                length = np.around(math.sqrt((latlong1[0] - latlong2[0]) ** 2 + (latlong1[1] - latlong2[1]) ** 2), 3)

            weight = 1.0
            graph.add_edge(source.childNodes[0].data, target.childNodes[0].data,
                           id=link.getAttribute("id"), weight=weight, length=length, index=idx)
    graph.graph["node_indices"] = []
    for idx, node in enumerate(graph.nodes()):
        graph.graph["node_indices"].append(node)

    return graph


def get_topology(args):
    if args.topology_file.endswith('.xml'):
        topology = read_sndlib_topology(args.topology_file)
    else:
        raise ValueError('Supplied topology is unknown')

    #x_p = np.array([0, 5]) 
    #y_p = np.array([0, 5])

    nx.draw_networkx(topology)
    #plt.plot(x_p, y_p)
    plt.show()
    
    return topology


def get_dcs(args, topology):
    topology.graph['source_nodes'] = []
    topology.graph['dcs'] = []
    if args.dc_placement == 'degree':
        degree = sorted(topology.degree(), key=itemgetter(1), reverse=True)
        for i in range(args.num_dcs):
            node = degree[i][0]
            topology.graph['dcs'].append(node)
            topology.nodes[node]['dc'] = True
        for i in range(args.num_dcs, topology.number_of_nodes()):
            node = degree[i][0]
            topology.graph['source_nodes'].append(node)
            topology.nodes[node]['dc'] = False
        return topology
    else:
        raise ValueError('Selected args.dc_placement not correct!')


def get_ksp(args, topology):
    k_shortest_paths = {}

    for idn1, n1 in enumerate(topology.graph['source_nodes']):
        for idn2, n2 in enumerate(topology.graph['dcs']):
            paths = get_k_shortest_paths(topology, n1, n2, args.k_paths)
            lengths = [get_path_weight(topology, path) for path in paths]
            objs = []
            for path, length in zip(paths, lengths):
                objs.append(Path(path, length))
            # both directions have the same paths, i.e., bidirectional symetrical links
            k_shortest_paths[n1, n2] = objs
            k_shortest_paths[n2, n1] = objs
    topology.graph['ksp'] = k_shortest_paths
    return topology