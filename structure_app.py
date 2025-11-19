# structure_app.py
import streamlit as st
import pandas as pd
import numpy as np
from anastruct import SystemElements
import matplotlib.pyplot as plt

st.set_page_config(page_title="Structural Analysis Tool (US Units)", layout="wide")
st.title("🛠️ 2D Frame & Truss Analysis Tool (US Customary Units)")

st.markdown("""
**Units Guide:**
- **Coordinates / Length:** Feet (ft)
- **Force:** Kips (k)
- **Distributed Load:** kips/ft (k/ft)
- **Modulus E:** ksi (kips/in²)
- **Moment of Inertia I:** in⁴
- **Cross-sectional Area A:** in²
""")

# --- SESSION STATE INITIALIZATION ---
if "elements" not in st.session_state:
    st.session_state["elements"] = []
if "nodes" not in st.session_state:
    st.session_state["nodes"] = pd.DataFrame([
        {"node_id": 1, "x": 0.0,  "y": 0.0},
        {"node_id": 2, "x": 20.0, "y": 0.0},
    ])
if "loads" not in st.session_state:
    st.session_state["loads"] = []

col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Define Structure")

    # --- A. NODES ---
    st.subheader("A. Nodes (ft)")
    edited_nodes = st.data_editor(
        st.session_state["nodes"],
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "node_id": st.column_config.NumberColumn("Node ID", min_value=1, step=1),
            "x": st.column_config.NumberColumn("X (ft)", format="%.3f"),
            "y": st.column_config.NumberColumn("Y (ft)", format="%.3f"),
        }
    )
    st.session_state["nodes"] = edited_nodes

    # --- B. MEMBERS ---
    st.subheader("B. Members & Section Properties")
    node_ids = edited_nodes["node_id"].tolist()

    with st.form("add_member_form"):
        st.write("**Connectivity**")
        c1, c2 = st.columns(2)
        start_node = c1.selectbox("Start Node", node_ids, key="start_sel")
        end_node = c2.selectbox("End Node", node_ids, index=1 if len(node_ids)>1 else 0, key="end_sel")

        st.write("**Section Properties**")
        cp1, cp2, cp3 = st.columns(3)
        E_ksi = cp1.number_input("E (ksi)", value=29000.0, min_value=0.1)
        I_in4 = cp2.number_input("I (in⁴)", value=510.0, min_value=0.001)
        A_in2 = cp3.number_input("A (in²)", value=14.6, min_value=0.001)

        submitted = st.form_submit_button("➕ Add Member")
        if submitted:
            if start_node == end_node:
                st.error("Start and end nodes must be different.")
            elif any(el["start"] == start_node and el["end"] == end_node for el in st.session_state["elements"]):
                st.warning("This member already exists.")
            else:
                st.session_state["elements"].append({
                    "start": start_node,
                    "end": end_node,
                    "E": E_ksi,
                    "I": I_in4,
                    "A": A_in2
                })
                st.success(f"Member {start_node}→{end_node} added.")

    if st.session_state["elements"]:
        st.write("**Current Members**")
        disp = []
        for i, el in enumerate(st.session_state["elements"]):
            disp.append({
                "Mem": i+1,
                "Nodes": f"{el['start']}→{el['end']}",
                "E (ksi)": el["E"],
                "I (in⁴)": el["I"],
                "A (in²)": el["A"],
            })
        st.dataframe(pd.DataFrame(disp), use_container_width=True, hide_index=True)

        if st.button("🗑️ Clear All Members", type="secondary"):
            st.session_state["elements"] = []
            st.rerun()

    # --- C. SUPPORTS ---
    st.subheader("C. Supports")
    support_config = {}
    for nid in node_ids:
        cols = st.columns([1.5, 1, 1, 1])
        cols[0].write(f"Node {nid}")
        if cols[1].checkbox("Fixed", key=f"fix_{nid}"):
            support_config[nid] = "fixed"
        elif cols[2].checkbox("Pinned", key=f"pin_{nid}"):
            support_config[nid] = "pinned"
        elif cols[3].checkbox("Roller", key=f"roll_{nid}"):
            support_config[nid] = "roller"

    # --- D. LOADS ---
    st.subheader("D. Loads")
    with st.form("add_load_form"):
        mem_options = list(range(1, len(st.session_state["elements"]) + 1))
        mem_labels = [f"Member {i}" for i in mem_options]

        selected_mem = st.selectbox(
            "Apply load to",
            options=mem_options,
            format_func=lambda x: mem_labels[x-1] if mem_options else "No members"
        ) if mem_options else None

        load_type = st.selectbox("Load Type", ["Point Load (k)", "Uniform Distributed Load (k/ft)"])
        mag = st.number_input("Magnitude (use negative for downward)", value=-10.0)

        location = None
        if "Point" in load_type:
            location = st.number_input("Distance from Start Node (ft)", min_value=0.0, value=10.0)

        add_load_btn = st.form_submit_button("➕ Add Load")
        if add_load_btn and selected_mem:
            load_data = {
                "element_id": selected_mem,
                "type": "point" if "Point" in load_type else "distributed",
                "value": float(mag)
            }
            if location is not None:
                load_data["location"] = float(location)

            st.session_state["loads"].append(load_data)
            st.success("Load added!")

    if st.session_state["loads"]:
        st.write("**Active Loads**")
        load_disp = []
        for i, ld in enumerate(st.session_state["loads"]):
            desc = f"{ld['value']:.2f} k{' @ ' + str(ld['location']) + ' ft' if ld['type']=='point' else ' k/ft uniform'}"
            load_disp.append({"#": i+1, "Member": ld["element_id"], "Load": desc})
        st.dataframe(pd.DataFrame(load_disp), hide_index=True)

        if st.button("🗑️ Clear All Loads", type="secondary"):
            st.session_state["loads"] = []

# ===================================================================
# ANALYSIS (Right Column)
# ===================================================================
with col2:
    st.header("2. Analysis Results")

    if not st.session_state["elements"]:
        st.info("👈 Define nodes, members, supports, and loads on the left to run analysis.")
        st.stop()

    # Create new anastruct system
    ss = SystemElements(EA=1e10, EI=1e10)  # temporary, will be overwritten

    # Maps
    user_to_ana_node = {}   # user node ID → anastruct node ID
    member_to_elements = {} # user member ID → list of anastruct element IDs

    # Step 1: Add all user-defined nodes
    node_coords = {}
    for _, row in edited_nodes.iterrows():
        nid_user = int(row["node_id"])
        x, y = float(row["x"]), float(row["y"])
        node_coords[nid_user] = (x, y)
        ana_nid = ss.add_node(x, y)
        user_to_ana_node[nid_user] = ana_nid

    # Step 2: Process each member (with automatic splitting at point loads)
    for mem_idx, el in enumerate(st.session_state["elements"]):
        user_mem_id = mem_idx + 1
        n1, n2 = el["start"], el["end"]
        x1, y1 = node_coords[n1]
        x2, y2 = node_coords[n2]
        L = np.sqrt((x2-x1)**2 + (y2-y1)**2)

        # Unit conversion
        E_ksf = el["E"] * 144.0          # ksi → ksf
        I_ft4 = el["I"] / (12**4)        # in⁴ → ft⁴
        A_ft2 = el["A"] / 144.0          # in² → ft²
        EI = E_ksf * I_ft4
        EA = E_ksf * A_ft2

        # Collect point loads on this member
        point_loads = [
            ld for ld in st.session_state["loads"]
            if ld["element_id"] == user_mem_id and ld["type"] == "point"
        ]
        point_loads.sort(key=lambda ld: ld.get("location", 0))

        # Build list of split points (0 and L always included)
        distances = [0.0]
        loads_at_dist = []
        for pl in point_loads:
            d = pl.get("location", 0)
            if 0 < d < L:
                distances.append(d)
                loads_at_dist.append(pl["value"])
        distances.append(L)

        element_ids_this_member = []

        # Create segments
        for i in range(len(distances)-1):
            d1, d2 = distances[i], distances[i+1]
            ratio1, ratio2 = d1/L, d2/L
            xa = x1 + ratio1*(x2-x1)
            ya = y1 + ratio1*(y2-y1)
            xb = x1 + ratio2*(x2-x1)
            yb = y1 + ratio2*(y2-y1)

            # Node IDs (reuse existing if possible)
            node1 = ss.find_node_id([xa, ya]) or ss.add_node(xa, ya)
            node2 = ss.find_node_id([xb, yb]) or ss.add_node(xb, yb)

            elem_id = ss.add_element(node1, node2, EA=EA, EI=EI)
            element_ids_this_member.append(elem_id)

            # Apply point load at the end of this segment (except last segment)
            if i < len(loads_at_dist):
                ss.point_load(node=node2, Fy=loads_at_dist[i])

        member_to_elements[user_mem_id] = element_ids_this_member

    # Step 3: Apply supports using mapped node IDs
    for user_nid, sup_type in support_config.items():
        if user_nid in user_to_ana_node:
            ana_nid = user_to_ana_node[user_nid]
            if sup_type == "fixed":
                ss.add_support_fixed(ana_nid)
            elif sup_type == "pinned":
                ss.add_support_hinged(ana_nid)
            elif sup_type == "roller":
                ss.add_support_roll(ana_nid)

    # Step 4: Apply distributed loads to all segments of the member
    for ld in st.session_state["loads"]:
        if ld["type"] == "distributed":
            seg_ids = member_to_elements.get(ld["element_id"], [])
            for seg_id in seg_ids:
                ss.q_load(q=ld["value"], element_id=seg_id)

    # Solve
    try:
        ss.solve()
    except Exception as e:
        st.error(f"⚠️ Solver failed: {e}")
        st.info("Common causes: insufficient supports, collinear members, or zero stiffness.")
        st.stop()

    # Display results
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Structure", "Moment (k-ft)", "Shear (k)", "Deflection (ft)", "Reactions"])

    with tab1:
        st.pyplot(ss.show_structure(show=False, figsize=(10,6)))
        st.caption("Blue dots at midpoints = point load application nodes")

    with tab2:
        st.pyplot(ss.show_bending_moment(show=False, figsize=(10,5)))
        st.caption("Bending Moment Diagram (k-ft)")

    with tab3:
        st.pyplot(ss.show_shear_force(show=False, figsize=(10,5)))
        st.caption("Shear Force Diagram (kips)")

    with tab4:
        factor = st.slider("Deflection scale factor", 10, 1000, 200, 50)
        st.pyplot(ss.show_displacement(show=False, factor=factor, figsize=(10,6)))
        st.caption("Vertical deflection in feet × scale factor (typically exaggerated)")

    with tab5:
        st.subheader("Reaction Forces")
        if not support_config:
            st.info("No supports defined.")
        else:
            rxn_data = []
            for user_nid, _ in support_config.items():
                ana_nid = user_to_ana_node[user_nid]
                res = ss.get_node_results_system(ana_nid)[0]
                rxn_data.append({
                    "Node": user_nid,
                    "Fx (k)": round(res["Fx"], 3),
                    "Fy (k)": round(res["Fy"], 3),
                    "Mz (k-ft)": round(res["Tzz"], 3),
                })
            st.table(pd.DataFrame(rxn_data))

    st.success("✅ Analysis completed successfully!")
