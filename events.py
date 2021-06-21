import logging

import routing_policies


def request_arrival(env, service):
    # logging.debug('Processing arrival {} for policy {} load {} seed {}'.format(service.service_id, env.policy, env.load, env.seed))

    success, dc, path = env.policy.route(service)

    if success:
        service.route = path
        env.provision_service(service)
    else:
        env.reject_service(service)

    env.setup_next_arrival() # schedules next arrival


def request_departure(env, service):
    env.release_path(service)

def disaster_arrival(env, disaster):
    pass

def disaster_departure(env, disaster):
    pass

''' 
Pegar o grafo como parametro, receber os links que deram problema
env = core.Environment(uargs, topology=topology)
disaster = [nodesDisaster[], linksDisaster[]]

Disaster() -> Retira (false) esses Edges do grafo.
''' 