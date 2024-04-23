import networkx as nx

SG=nx.Graph()
SG.add_nodes_from("HelloWorld")
SG.add_edges_from([(0, 1), (1, 2), (3,4), (6,8)])
print(SG)