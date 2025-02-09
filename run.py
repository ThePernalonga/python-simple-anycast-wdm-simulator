import logging
logging.basicConfig(format='%(asctime)s\t%(name)-12s\t%(threadName)s\t%(message)s', level=logging.DEBUG)

import argparse
import copy
import pickle
import datetime
import time
import shutil
import sys
#import git
import os
import numpy as np
import networkx as nx
from multiprocessing import Pool
from multiprocessing import Manager

import core
import graph
import plots
import routing_policies


def run(uargs):
    start_time = time.time()

    topology = graph.get_topology(uargs)
    topology = graph.get_dcs(uargs, topology)
    topology = graph.get_ksp(uargs, topology)
    env = core.Environment(uargs, topology=topology)

    logger = logging.getLogger('run')

    # in this case, a configuration changes only the load of the network
    exec_policies = ['CADC', 'FADC', 'FLB']
    loads = [x for x in range(args.min_load, args.max_load + 1, args.load_step)]

    final_output_folder = env.output_folder + '/' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fUTC')
    env.output_folder = final_output_folder

    if not os.path.isdir('./results/' + env.output_folder):
        os.makedirs('./results/' + env.output_folder)
        logger.debug(f'creating folder {env.output_folder}')

    # copy current version of files
    with open('./results/{}/0-info.txt'.format(env.output_folder), 'wt') as file:
        width = 20
        print('Date (UTC):'.ljust(width), datetime.datetime.now(datetime.timezone.utc), file=file)
        print('Date (local):'.ljust(width), datetime.datetime.now(), file=file)
        #repo = git.Repo()
        #print('Commit date:'.ljust(width),
        #      datetime.datetime.fromtimestamp(repo.head.object.committed_date).strftime('%Y-%m-%d %H:%M:%S'),
        #      file=file)
        #print('Author:'.ljust(width), repo.head.object.committer, file=file)
        #print('GIT hexsha:'.ljust(width), repo.head.object.hexsha, file=file)
        print('Command:'.ljust(width), ' '.join(sys.argv), file=file)
        print('Arguments:'.ljust(width), args, file=file)

    # copy current version of files
    shutil.copytree('./', f'./results/{env.output_folder}/source-code/',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.md', 'results', 'LICENSE', '*.ipynb'))

    manager = Manager()
    results = manager.dict()
    for policy in exec_policies: # runs the simulations for two policies
        results[policy] = {load: manager.list() for load in loads}

    envs = []
    for policy in exec_policies: # runs the simulations for two policies
        for load in loads:
            if policy == 'CADC':
                policy_instance = routing_policies.ClosestAvailableDC()
            elif policy == 'FADC':
                policy_instance = routing_policies.FarthestAvailableDC()
            elif policy == 'FLB':
                policy_instance = routing_policies.FullLoadBalancing()
            else:
                raise ValueError('Policy was not configured correctly (value set to {})'.format(policy))
            env_topology = copy.deepcopy(topology) # makes a deep copy of the topology object
            env_t = core.Environment(uargs,
                                     topology=env_topology,
                                     results=results,
                                     load=load,
                                     policy=policy_instance,
                                     seed=len(exec_policies) * load,
                                     output_folder=env.output_folder)
            envs.append(env_t)
            # code for debugging purposes -- it runs without multithreading
            # if load == 400 and policy == 'CADC':
            #     core.run_simulation(env_t)

    logger.debug(f'Starting pool of simulators with {uargs.threads} threads')
    # use the code above to keep updating the final plot as the simulation progresses
    with Pool(processes=uargs.threads) as p:
        result_pool = p.map_async(core.run_simulation, envs)
        p.close()

        done = False
        while not done:
            if result_pool.ready():
                done = True
            else:
                time.sleep(uargs.temporary_plot_every)
                plots.plot_final_results(env, results, start_time)

    # if you do not want periodical updates, you can use the following code
    # with Pool(processes=uargs.threads) as p:
    #     p.map(core.run_simulation, envs)
    #     p.close()
    #     p.join()
    #     logging.debug("Finished the threads")

    # consolidating statistics
    plots.plot_final_results(env, results, start_time)

    with open('./results/{}/final_results.h5'.format(env.output_folder), 'wb') as file:
        realized_results = dict(results)
        for k1,v1 in results.items():
            realized_results[k1] = dict(v1);
            for k2,v2 in results[k1].items():
                realized_results[k1][k2] = list(v2)
        pickle.dump({
            'args': uargs,
            'env': env,
            'results': realized_results,
            'policies': [policy for policy in exec_policies],
            'loads': loads,
            'timedelta': datetime.timedelta(seconds=(time.time() - start_time)),
            'datetime': datetime.datetime.fromtimestamp(time.time())
        }, file)

    logger.debug('Finishing simulation after {}'.format(datetime.timedelta(seconds=(time.time() - start_time))))


if __name__ == '__main__':
    env = core.Environment()

    parser = argparse.ArgumentParser()
    parser.add_argument('--plot_simulation_progress', default=False, action='store_true',
                        help='Plot summary for each seed simulated (default=False)')
    parser.add_argument('-tf', '--topology_file', default=env.topology_file, help='Network topology file to be used')
    parser.add_argument('-a', '--num_arrivals', type=int, default=env.num_arrivals,
                        help='Number of arrivals per episode to be generated (default={})'.format(env.num_arrivals))
    parser.add_argument('-k', '--k_paths', type=int, default=env.k_paths,
                        help='Number of k-shortest-paths to be considered (default={})'.format(env.k_paths))
    parser.add_argument('-d', '--num_dcs', type=int, default=env.num_dcs,
                        help='Number of datacenters to be placed (default={})'.format(env.num_dcs))
    parser.add_argument('--dc_placement', default=env.dc_placement,
                        help='DC placement criteria (default={})'.format(env.dc_placement))
    parser.add_argument('-t', '--threads', type=int, default=env.threads,
                        help='Number of threads to be used to run the simulations (default={})'.format(
                            env.threads))
    parser.add_argument('--min_load', type=int, default=300,
                        help='Load in Erlangs of the traffic generated (mandatory)')
    parser.add_argument('--max_load', type=int, default=700,
                        help='Load in Erlangs of the traffic generated (mandatory)')
    parser.add_argument('--load_step', type=int, default=50,
                        help='Load in Erlangs of the traffic generated (default: {})'.format(50))
    parser.add_argument('-s', '--seed', type=int, default=env.seed,
                        help='Seed of the random numbers (default={})'.format(env.seed))
    parser.add_argument('-ns', '--num_seeds', type=int, default=env.num_seeds,
                        help='Number of seeds to run for each configuration (default={})'.format(env.num_seeds))
    te = 5
    parser.add_argument('-te', '--temporary_plot_every', type=int, default=te, #TODO: adjust for your needs
                        help='Time interval for plotting intermediate statistics of the simulation in seconds (default={})'.format(te))
    parser.add_argument('-o', '--output_folder', default=env.output_folder,
                        help='Output folder inside results (default={})'.format(env.output_folder))
    args = parser.parse_args()

   """" 
    brokenNodes = ["A", "B"]

    for node in brokenNodes:

    brokenLinks = ["A", "B"]
    core.Disaster(graph, )
    """
    run(args)

    
