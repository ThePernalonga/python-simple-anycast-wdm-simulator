import logging
import random
import heapq
import multiprocessing
import numpy as np
from datetime import datetime

import events
import plots
import routing_policies


class Environment:

    def __init__(self, args=None, topology=None, results=None, seed=None, load=None, policy=None, id_simulation=None,
                 output_folder=None):

        if args is not None and hasattr(args, 'mean_service_holding_time'):
            self.mean_service_holding_time = args.mean_service_holding_time
        else:
            self.mean_service_holding_time = 86400.0 # service holding time in seconds (54000 sec = 15 h)

        self.load = 0.0
        self.mean_service_inter_arrival_time = 0.0
        if args is not None and hasattr(args, 'load') and load is None:
            self.set_load(load=args.load)
        elif load is not None: # load through parameter has precedence over argument
            self.set_load(load=load)
        else:
            self.set_load(load=50)

        # num_seeds defines the number of seeds (simulations) to be run for each configuration
        if args is not None and hasattr(args, "num_seeds"):
            self.num_seeds = args.num_seeds
        else:
            self.num_seeds = 5

        # defines the number of DCs to be placed in the topology
        if args is not None and hasattr(args, "num_dcs"):
            self.num_dcs = args.num_dcs
        else:
            self.num_dcs = 2

        # defines the number of DCs to be placed in the topology
        if args is not None and hasattr(args, "dc_placement"):
            self.dc_placement = args.dc_placement
        else:
            self.dc_placement = 'degree'

        if args is not None and hasattr(args, "plot_simulation_progress"):
            self.plot_simulation_progress = args.plot_simulation_progress
        else:
            self.plot_simulation_progress = False

        if args is not None and hasattr(args, "num_arrivals"):
            self.num_arrivals = args.num_arrivals
        else:
            self.num_arrivals = 10000

        if args is not None and hasattr(args, "k_paths"):
            self.k_paths = args.k_paths
        else:
            self.k_paths = 5

        if args is not None and hasattr(args, 'threads'):
            self.threads = args.threads
        else:
            self.threads = 6

        if args is not None and hasattr(args, 'topology_file'):
            self.topology_file = args.topology_file
            self.topology_name = args.topology_file.split('.')[0]
        else:
            self.topology_file = "test.xml"#"nobel-us.xml" #"test-topo.xml"
            self.topology_name = 'test'
            # self.topology_file = "simple"  # "nobel-us.xml" #"test-topo.xml"
            # self.topology_name = 'simple'

        if args is not None and hasattr(args, "resource_units_per_link"):
            self.resource_units_per_link = args.resource_units_per_link
        else:
            self.resource_units_per_link = 80

        if policy is not None:
            self.policy = policy # parameter has precedence over argument
            self.policy.env = self
        else:
            self.policy = routing_policies.ClosestAvailableDC() # closest DC by default
            self.policy.env = self

        if topology is not None:
            self.topology = topology

        if seed is not None:
            self.seed = seed
            self.rng = random.Random(seed)
        else:
            self.seed = 42
            self.rng = random.Random(42)

        if results is not None:
            self.results = results
        else:
            self.results = [] # initiates with an empty local results vector

        if id_simulation is not None:
            self.id_simulation = id_simulation
        else:
            self.id_simulation = 0

        self.track_stats_every = 100 # frequency at which results are saved
        self.plot_tracked_stats_every = 1000 # frequency at which results are plotted
        self.tracked_results = {}
        self.tracked_statistics = ['request_blocking_ratio', 'average_link_usage', 'average_node_usage']
        for obs in self.tracked_statistics:
            self.tracked_results[obs] = []

        self.events = []  # event queue
        self._processed_arrivals = 0
        self._rejected_services = 0
        self.current_time = 0.0

        if output_folder is not None:
            self.output_folder = output_folder
        elif args is not None and hasattr(args, "output_folder"):
            self.output_folder = args.output_folder
        else:
            self.output_folder = 'data'

        self.plot_formats = ['pdf', 'svg'] # you can configure this to other formats such as PNG, SVG

    def compute_simulation_stats(self):
        # run here the code to summarize statistics from this specific run
        if self.plot_simulation_progress:
            plots.plot_simulation_progress(self)
        # add here the code to include other statistics you may want
        self.results[self.policy.name][self.load].append({
            'request_blocking_ratio': self.get_request_blocking_ratio(),
            'average_link_usage': np.mean([self.topology[n1][n2]['utilization'] for n1, n2 in self.topology.edges()]),
            'individual_link_usage': [self.topology[n1][n2]['utilization'] for n1, n2 in self.topology.edges()],
            'average_node_usage': np.mean([self.topology.nodes[node]['utilization'] for node in self.topology.graph['dcs']]),
            'individual_node_usage': {node: self.topology.nodes[node]['utilization'] for node in self.topology.graph['dcs']}
        })

    def reset(self, seed=None, id_simulation=None):
        self.events = [] # event queue
        self._processed_arrivals = 0
        self._rejected_services = 0
        self.current_time = 0.0

        for obs in self.tracked_statistics:
            self.tracked_results[obs] = []

        if seed is not None:
            self.seed = seed
            self.rng = random.Random(seed)
        if id_simulation is not None:
            self.id_simulation = id_simulation

        # (re)-initialize the graph
        self.topology.graph['running_services'] = []
        self.topology.graph['services'] = []
        for idx, lnk in enumerate(self.topology.edges()):
            self.topology[lnk[0]][lnk[1]]['available_units'] = self.resource_units_per_link
            self.topology[lnk[0]][lnk[1]]['total_units'] = self.resource_units_per_link
            self.topology[lnk[0]][lnk[1]]['services'] = []
            self.topology[lnk[0]][lnk[1]]['running_services'] = []
            self.topology[lnk[0]][lnk[1]]['id'] = idx
            self.topology[lnk[0]][lnk[1]]['utilization'] = 0.0
            self.topology[lnk[0]][lnk[1]]['last_update'] = 0.0
        for idx, node in enumerate(self.topology.nodes()):
            if self.topology.nodes[node]['dc']:
                self.topology.nodes[node]['available_units'] = self.topology.degree(node) * self.resource_units_per_link
                self.topology.nodes[node]['total_units'] = self.topology.degree(node) * self.resource_units_per_link
                self.topology.nodes[node]['services'] = []
                self.topology.nodes[node]['running_services'] = []
                self.topology.nodes[node]['id'] = idx
                self.topology.nodes[node]['utilization'] = 0.0
                self.topology.nodes[node]['last_update'] = 0.0
            else:
                self.topology.nodes[node]['available_units'] = 0
                self.topology.nodes[node]['total_units'] = 0
        self.setup_next_arrival()
        
    def setup_next_arrival(self):
        """
        Returns the next arrival to be scheduled in the simulator
        """
        if self._processed_arrivals > self.num_arrivals:
            return None # returns None when all arrivals have been processed
        at = self.current_time + self.rng.expovariate(1 / self.mean_service_inter_arrival_time)

        ht = self.rng.expovariate(1 / self.mean_service_holding_time)
        src = self.rng.choice([x for x in self.topology.graph['source_nodes']])
        src_id = self.topology.graph['node_indices'].index(src)

        self._processed_arrivals += 1

        if self._processed_arrivals % self.track_stats_every == 0:
            self.tracked_results['request_blocking_ratio'].append(self.get_request_blocking_ratio())
            self.tracked_results['average_link_usage'].append(np.mean([(self.topology[n1][n2]['total_units'] - self.topology[n1][n2]['available_units']) / self.topology[n1][n2]['total_units'] for n1, n2 in self.topology.edges()]))
            self.tracked_results['average_node_usage'].append(np.mean([(self.topology.nodes[node]['total_units'] -
                                                                        self.topology.nodes[node]['available_units']) /
                                                                       self.topology.nodes[node]['total_units'] for node
                                                                       in self.topology.graph['dcs']]))
        if self._processed_arrivals % self.plot_tracked_stats_every == 0:
            plots.plot_simulation_progress(self)

        #TODO: number of units necessary can also be randomly selected, now it's always one
        next_arrival = Service(self._processed_arrivals, at, ht, src, src_id, network_units=1, computing_units=1)
        self.add_event(Event(next_arrival.arrival_time, events.request_arrival, next_arrival))

    def set_load(self, load=None, mean_service_holding_time=None):
        if load is not None:
            self.load = load
        if mean_service_holding_time is not None:
            self.mean_service_holding_time = mean_service_holding_time  # service holding time in seconds (10800 sec = 3 h)
        self.mean_service_inter_arrival_time = 1 / float(self.load / float(self.mean_service_holding_time))

    def add_event(self, event):
        """
        Adds an event to the event list of the simulator.
        This implementation is based on the functionalities of heapq: https://docs.python.org/2/library/heapq.html
        :param event:
        :return: None
        """
        #self.debug("time={}; event={}".format(event.time, event.call))
        heapq.heappush(self.events, (event.time, event))

    def provision_service(self, service):
        service.destination = service.route.node_list[-1]
        service.destination_id = self.topology.graph['node_indices'].index(service.destination)

        # provisioning service at the DC
        self.topology.nodes[service.destination]['available_units'] -= service.computing_units
        self.topology.nodes[service.destination]['services'].append(service)
        self.topology.nodes[service.destination]['running_services'].append(service)
        self._update_node_stats(service.destination)

        # provisioning the path
        for i in range(len(service.route.node_list) - 1):
            self.topology[service.route.node_list[i]][service.route.node_list[i + 1]]['available_units'] -= service.network_units
            self.topology[service.route.node_list[i]][service.route.node_list[i + 1]]['services'].append(service)
            self.topology[service.route.node_list[i]][service.route.node_list[i + 1]]['running_services'].append(service)
            self._update_link_stats(service.route.node_list[i], service.route.node_list[i + 1])
        service.provisioned = True

        self.topology.graph['running_services'].append(service)
        self._update_network_stats()

        # schedule departure
        self.add_event(Event(service.arrival_time + service.holding_time, events.request_departure, service))

    def reject_service(self, service):
        service.provisioned = False
        self.topology.graph['services'].append(service)
        self._rejected_services += 1

    def release_path(self, service):
        # provisioning service at the DC
        self.topology.nodes[service.destination]['available_units'] += service.computing_units
        self.topology.nodes[service.destination]['running_services'].remove(service)
        self._update_node_stats(service.destination)
        for i in range(len(service.route.node_list) - 1):
            self.topology[service.route.node_list[i]][service.route.node_list[i + 1]]['available_units'] += service.network_units
            self.topology[service.route.node_list[i]][service.route.node_list[i + 1]]['running_services'].remove(service)
            self._update_link_stats(service.route.node_list[i], service.route.node_list[i + 1])
        self._update_network_stats()

    def _update_link_stats(self, node1, node2):
        """
        Updates link statistics following a time-weighted manner.
        """
        last_update = self.topology[node1][node2]['last_update']
        time_diff = self.current_time - self.topology[node1][node2]['last_update']
        if self.current_time > 0:
            last_util = self.topology[node1][node2]['utilization']
            cur_util = (self.resource_units_per_link - self.topology[node1][node2]['available_units']) / self.resource_units_per_link
            # utilization is weighted by the time
            utilization = ((last_util * last_update) + (cur_util * time_diff)) / self.current_time
            self.topology[node1][node2]['utilization'] = utilization
        self.topology[node1][node2]['last_update'] = self.current_time

    def _update_node_stats(self, node):
        """
        Updates node statistics following a time-weighted manner.
        """
        last_update = self.topology.nodes[node]['last_update']
        time_diff = self.current_time - self.topology.nodes[node]['last_update']
        if self.current_time > 0:
            last_util = self.topology.nodes[node]['utilization']
            cur_util = (self.topology.nodes[node]['total_units'] - self.topology.nodes[node]['available_units']) / self.topology.nodes[node]['total_units']
            # utilization is weighted by the time
            utilization = ((last_util * last_update) + (cur_util * time_diff)) / self.current_time
            self.topology.nodes[node]['utilization'] = utilization
        self.topology.nodes[node]['last_update'] = self.current_time

    def _update_network_stats(self):
        """
        Updates statistics related to the entire network. To be implemented using the particular stats necessary for your problem.
        """
        pass

    def get_request_blocking_ratio(self):
        return float(self._rejected_services) / float(self._processed_arrivals)


def run_simulation(env):
    """
    Launches the simulation for one particular configuration represented by the env object.
    """
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(logging.INFO)
    logger.info(f'Running simulation for load {env.load} and policy {env.policy.name}')

    for seed in range(env.num_seeds):
        env.reset(seed=env.seed + seed, id_simulation=seed) # adds to the general seed
        logger.info(f'Running simulation {seed} for policy {env.policy.name} and load {env.load}')
        while len(env.events) > 0:
            event_tuple = heapq.heappop(env.events)
            time = event_tuple[0]
            env.current_time = time
            event = event_tuple[1]
            event.call(env, event.params)

        env.compute_simulation_stats()
    # prepare observations
    logger.info(f'Finishing simulation for load {env.load} and policy {env.policy.name}')


"""class Disaster:

    def __init__(self, graph, brokenNodes, brokenLinks):

    # Save the IDs of the broken nodes and links 
        self.disastNodes = brokenNodes
        self.disastLinks = brokenLinks

    def arrival_time():
      time = datetime.now()
        
    #def duration():
        
    #def failed_links():
        
    #def failed_nodes():

    def Arrival_F(self):
        disastNodes = brokenNodes
        disastLinks = brokenLinks
        
    def Depart_F(self):
        pass

"""

class Service:
    """"
    Class that defines one service in the system.
    """
    def __init__(self, serv_id, at, ht, src, src_id, network_units=1, computing_units=1):
        self.service_id = serv_id
        self.arrival_time = at
        self.holding_time = ht
        self.source = src
        self.source_id = src_id
        self.destination = None
        self.destination_id = None
        self.network_units = network_units # number of network units required
        self.computing_units = computing_units # number of CPUs required at the DC
        self.route = None # route to be followed
        self.provisioned = False # whether the service was provisioned or not


class Event:
    """
    Class that models one event of the event queue.
    """
    def __init__(self, time=-1, call=None, params=None):
        self.time = time
        self.call = call
        self.params = params
