# structure_app.py
import streamlit as st
import pandas as pd
import numpy as np
from anastruct import SystemElements
import matplotlib.pyplot as plt

st.set_page_config(page_title="2D Frame & Truss Analysis (US Units)", layout="wide")
st.title("2D Frame & Truss Analysis Tool (US Customary Units)")

st.markdown("""
**Units**
- Length / Coordinates → **feet (ft)**
- Force → **kips (k)**
- Distributed load → **kips/ft**
- E → **ksi**, I → **in⁴**, A → **in²**
""")

# ── Session State ─────────────────────────────────────────────────────
if "elements" not in st.session_state:
    st.session_state.elements = []
if "nodes" not in st.session_state:
    st.session_state.nodes = pd.DataFrame([
        {"node_id": 1, "x": 0.0,  "y": 0.0},
        {"node_id": 2, "x": 20.0, "y": 0.0},
    ])
if "loads" not in st.session_state:
    st.session_state.loads = []

col1, col2 = st.columns([1, 2])

# ── LEFT PANEL ───────────────────────────────────────────────────────
with col1:
    st.header("1. Define Structure")

    # Nodes
    st.subheader("A. Nodes (ft)")
    edited_nodes = st.data_editor(
        st.session_state.nodes,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "node_id": st.column_config.NumberColumn("Node ID", min_value=1, step=1),
            "x": st.column_config.NumberColumn("X (ft)"),
            "y": st.column_config.NumberColumn("Y (ft)"),
        },
    )
    st.session_state.nodes = edited_nodes

    node_ids = edited_nodes["node_id"].astype(int).tolist()

    # Members
    st.subheader("B. Members & Section Properties")
    with st.form("add_member"):
        c1, c2 = st.columns(2)
        start = c1.selectbox("Start Node", node_ids, key="s1")
        end   = c2.selectbox("End Node",   node_ids, index=1, key="e1")

        p1, p2, p3 = st.columns(3)
        E = p1.number_input("E (ksi)", value=29000.0, min_value=0.1)
        I = p2.number_input("I (in⁴)", value=510.0, min_value=0.001)
        A = p3.number_input("A (in²)", value=14.6, min_value=0.001)

        if st.form_submit_button("Add Member"):
            if start == end:
                st.error("Start and end nodes must be different")
            elif any(m["start"]==start and m["end"]==end for m in st.session_state.elements):
                st.warning("Member already exists")
            else:
                st.session_state.elements.append({"start":start, "end":end, "E":E, "I":I, "A":A})
                st.success("Member added")

    if st.session_state.elements:
        disp = [{"Mem":i+1,
                 "Nodes":f"{m['start']}→{m['end']}",
                 "E (ksi)":m["E"], "I (in⁴)":m["I"], "A (in²)":m["A"]}
                for i,m in enumerate(st.session_state.elements)]
        st.dataframe(pd.DataFrame(disp), hide_index=True, use_container_width=True)
        if st.button("Clear Members"):
            st.session_state.elements = []

    # Supports
    st.subheader("C. Supports")
    supports = {}
    for nid in node_ids:
        c = st.columns([1.5,1,1,1])
        c[0].write(f"Node {nid}")
        if c[1].checkbox("Fixed",  key=f"f{nid}"): supports[nid] = "fixed"
        elif c[2].checkbox("Pinned", key=f"p{nid}"): supports[nid] = "pinned"
        elif c[3].checkbox("Roller",key=f"r{nid}"): supports[nid] = "roller"

    # Loads
    st.subheader("D. Loads")
    with st.form("add_load"):
        mem_ids = list(range(1, len(st.session_state.elements)+1))
        mem = st.selectbox("Member", options=mem_ids, format_func=lambda x: f"Member {x}") if mem_ids else None
        typ = st.selectbox("Type", ["Point Load (k)", "Uniform Distributed (k/ft)"])
        mag = st.number_input("Magnitude (negative = downward)", value=-10.0)
        loc = None
        if "Point" in typ:
            loc = st.number_input("Distance from start (ft)", min_value=0.0, value=10.0)

        if st.form_submit_button("Add Load") and mem:
            ld = {"element_id": mem, "type": "point" if "Point" in typ else "distributed", "value": float(mag)}
            if loc is not None:
                ld["location"] = float(loc)
            st.session_state.loads.append(ld)
            st.success("Load added")

    if st.session_state.loads:
        ldisp = []
        for i, l in enumerate(st.session_state.loads):
            txt = f"{l['value']:.2f} k"
            if l["type"]=="point":
                txt += f" @ {l.get('location',0):.2f} ft"
            else:
                txt += " uniform"
            ldisp.append({"#":i+1, "Mem":l["element_id"], "Load":txt})
        st.dataframe(pd.DataFrame(ldisp), hide_index=True)
        if st.button("Clear Loads"):
            st.session_state.loads = []

# ── RIGHT PANEL – ANALYSIS ─────────────────────────────────────────────
with col2:
    st.header("2. Analysis Results")

    if not st.session_state.elements:
        st.info("Define the structure on the left first.")
        st.stop()

    ss = SystemElements()

    # Maps
    user_to_ana_node = {}      # user node id → anastruct node id
    member_to_elements = {}    # user member id → list of anastruct element ids

    # ---- Step 1: Create all nodes (automatically via first element that uses them) ----
    node_coords = {int(row.node_id): (float(row.x), float(row.y))
                   for row in edited_nodes.itertuples()}

    # ---- Step 2: Build members (with splitting at point loads) ----
    for mem_idx, mem in enumerate(st.session_state.elements):
        user_mem_id = mem_idx + 1
        n1, n2 = mem["start"], mem["end"]
        x1, y1 = node_coords[n1]
        x2, y2 = node_coords[n2]
        L = np.hypot(x2-x1, y2-y1)

        # Unit conversion
        EA = mem["E"] * 144 * (mem["A"]/144)      # ksi·in² → k·ft
        EI = mem["E"] * 144 * (mem["I"]/(12**4))  # ksi·in⁴ → k·ft³

        # Point loads on this member
        point_loads = [ld for ld in st.session_state.loads
                       if ld["element_id"]==user_mem_id and ld["type"]=="point"]
        point_loads.sort(key=lambda ld: ld.get("location",0))

        distances = [0.0]
        forces    = []
        for pl in point_loads:
            d = pl.get("location",0)
            if 0 < d < L:
                distances.append(d)
                forces.append(pl["value"])
        distances.append(L)

        elem_ids = []

        for i in range(len(distances)-1):
            d1, d2 = distances[i], distances[i+1]
            ratio1, ratio2 = d1/L, d2/L
            xa = x1 + ratio1*(x2-x1)
            ya = y1 + ratio1*(y2-y1)
            xb = x1 + ratio2*(x2-x1)
            yb = y1 + ratio2*(y2-y1)

            # Find or create nodes
            node1 = ss.find_node_id([xa, ya]) or ss.add_element(location=[[xa, ya], [xa, ya]], EA=EA, EI=EI)  # dummy, will be replaced
            node2 = ss.find_node_id([xb, yb])

            # Proper element creation using coordinate pairs (creates nodes automatically)
            elem_id = ss.add_element(location=[[xa, ya], [xb, yb]], EA=EA, EI=EI)
            elem_ids.append(elem_id)

            # Apply point load at the end of this segment (except last segment)
            if i < len(forces):
                end_node = ss.element_map[elem_id].node_id2
                ss.point_load(node_id=end_node, Fy=forces[i])

        member_to_elements[user_mem_id] = elem_ids

    # ---- Step 3: Map user nodes → anastruct nodes (now they exist) ----
    for user_id, (x, y) in node_coords.items():
        ana_id = ss.find_node_id([x, y])
        if ana_id is None:
            st.error(f"Could not locate node {user_id} – this should not happen")
        user_to_ana_node[user_id] = ana_id

    # ---- Step 4: Apply supports ----
    for user_id, typ in supports.items():
        nid = user_to_ana_node[user_id]
        if typ == "fixed":
            ss.add_support_fixed(node_id=nid)
        elif typ == "pinned":
            ss.add_support_hinged(node_id=nid)
        elif typ == "roller":
            ss.add_support_roll(node_id=nid)

    # ---- Step 5: Apply distributed loads ----
    for ld in st.session_state.loads:
        if ld["type"] == "distributed":
            for eid in member_to_elements.get(ld["element_id"], []):
                ss.q_load(q=ld["value"], element_id=eid)

    # ---- Solve ----
    try:
        ss.solve()
    except Exception as e:
        st.error(f"Solver error: {e}")
        st.stop()

    # ---- Results ----
    t1, t2, t3, t4, t5 = st.tabs(["Structure", "Moment (k-ft)", "Shear (k)", "Deflection", "Reactions"])

    with t1:
        st.pyplot(ss.show_structure(show=False))
    with t2:
        st.pyplot(ss.show_bending_moment(show=False))
    with t3:
        st.pyplot(ss.show_shear_force(show=False))
    with t4:
        factor = st.slider("Deflection scale", 50, 1000, 300, step=50)
        st.pyplot(ss.show_displacement(factor=factor, show=False))
    with t5:
        st.subheader("Reactions")
        if not supports:
            st.info("No supports defined")
        else:
            rows = []
            for uid, _ in supports.items():
                nid = user_to_ana_node[uid]
                res = ss.get_node_results_system(nid)[0]
                rows.append({
                    "Node": uid,
                    "Fx (k)": round(res["Fx"], 3),
                    "Fy (k)": round(res["Fy"], 3),
                    "Mz (k-ft)": round(res["Tzz"], 3),
                })
            st.table(pd.DataFrame(rows))

    st.success("Analysis completed!")
