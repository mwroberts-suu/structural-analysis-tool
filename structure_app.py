import streamlit as st
import pandas as pd
import numpy as np # Added for coordinate math
from anastruct import SystemElements
import matplotlib.pyplot as plt

st.set_page_config(page_title="Structural Analysis (US Units)", layout="wide")
st.title("Structural Analysis Tool (US Units)")

st.markdown("""
**Units Guide:**
* **Length/Coordinates:** Feet (ft)
* **Force:** Kips (k)
* **Distributed Load:** Kips per foot (k/ft)
* **Modulus (E):** ksi (kips/in²)
* **Properties (I, A):** in⁴, in²
""")

# --- INITIALIZE SESSION STATE ---
if "elements" not in st.session_state:
    st.session_state["elements"] = []
if "nodes" not in st.session_state:
    st.session_state["nodes"] = pd.DataFrame([
        {"node_id": 1, "x": 0.0, "y": 0.0},
        {"node_id": 2, "x": 10.0, "y": 0.0},
    ])
if "loads" not in st.session_state:
    st.session_state["loads"] = []

col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Define Structure")
    
    # --- A. NODES ---
    st.subheader("A. Nodes")
    st.caption("Enter coordinates in **FEET**.")
    edited_nodes = st.data_editor(st.session_state["nodes"], num_rows="dynamic", hide_index=True)
    
    # --- B. MEMBERS ---
    st.subheader("B. Members & Section Properties")
    node_ids = edited_nodes["node_id"].tolist()
    
    with st.form("add_element"):
        st.write("**Connectivity**")
        c1, c2 = st.columns(2)
        start_node = c1.selectbox("Start Node", node_ids)
        end_node = c2.selectbox("End Node", node_ids, index=min(1, len(node_ids)-1))
        
        st.write("**Section Properties**")
        cp1, cp2, cp3 = st.columns(3)
        
        E_ksi = cp1.number_input("E (ksi)", value=29000.0)
        I_in4 = cp2.number_input("I (in⁴)", value=204.0)
        A_in2 = cp3.number_input("Area (in²)", value=7.65)
        
        add_elem = st.form_submit_button("Add Member")
        
        if add_elem:
            if start_node != end_node:
                st.session_state["elements"].append({
                    "start": start_node,
                    "end": end_node,
                    "E": E_ksi,
                    "I": I_in4,
                    "A": A_in2
                })
            else:
                st.error("Nodes must be different.")

    if st.session_state["elements"]:
        st.write("Current Members:")
        display_data = []
        for i, el in enumerate(st.session_state["elements"]):
            display_data.append({
                "Mem": i+1,
                "Nodes": f"{el['start']}->{el['end']}",
                "E (ksi)": el['E'],
                "I (in⁴)": el['I'],
                "A (in²)": el['A']
            })
        st.table(pd.DataFrame(display_data))
        
        if st.button("Clear Members"):
            st.session_state["elements"] = []
    
    # --- C. SUPPORTS ---
    st.subheader("C. Supports")
    support_data = []
    for nid in node_ids:
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        c1.write(f"Node {nid}")
        if c2.checkbox("Fixed", key=f"fix_{nid}"): support_data.append((nid, "fixed"))
        elif c3.checkbox("Pin", key=f"pin_{nid}"): support_data.append((nid, "pinned"))
        elif c4.checkbox("Roll", key=f"roll_{nid}"): support_data.append((nid, "roller"))

    # --- D. LOADS ---
    st.subheader("D. Loads")
    with st.form("add_load"):
        element_indices = range(len(st.session_state["elements"]))
        element_labels = [f"Member {i+1}" for i in element_indices]
        
        selected_elem_idx = st.selectbox("Apply to Member", element_indices, format_func=lambda x: element_labels[x]) if element_indices else None
        
        c1, c2 = st.columns(2)
        load_type = c1.selectbox("Type", ["Point Load (k)", "Distributed Load (k/ft)"])
        
        mag = c2.number_input("Magnitude (k or k/ft)", value=-1.0)
        st.caption("Negative = Downward")
        
        loc = 0.0
        if "Point" in load_type:
            loc = st.number_input("Location (ft from Start Node)", min_value=0.0, value=5.0)
        
        if st.form_submit_button("Add Load") and selected_elem_idx is not None:
            st.session_state["loads"].append({
                "type": "point" if "Point" in load_type else "distributed",
                "element_id": selected_elem_idx + 1,
                "value": mag,
                "location": loc
            })

    if st.session_state["loads"]:
        st.write("Active Loads:")
        load_tbl = []
        for l in st.session_state["loads"]:
            desc = f"{l['value']} k" if l['type'] == 'point' else f"{l['value']} k/ft"
            if l['type'] == 'point': desc += f" @ {l['location']} ft"
            load_tbl.append({"Member": l['element_id'], "Load": desc})
        st.table(pd.DataFrame(load_tbl))
        if st.button("Clear Loads"):
            st.session_state["loads"] = []

with col2:
    st.header("2. Analysis Results")
    
    if not st.session_state["elements"]:
        st.info("Please define the structure on the left.")
    else:
        ss = SystemElements()
        node_map = {row['node_id']: [row['x'], row['y']] for i, row in edited_nodes.iterrows()}
        
        # --- INTELLIGENT BUILDER LOGIC ---
        # This tracks which anastruct Element IDs belong to which User Member ID
        # member_map = { user_member_id: [anastruct_id_1, anastruct_id_2] }
        member_map = {}
        current_ana_id = 1
        
        # Pre-process elements to handle Point Load splitting
        for i, el in enumerate(st.session_state["elements"]):
            user_id = i + 1
            start_node_id = el['start']
            end_node_id = el['end']
            
            if start_node_id in node_map and end_node_id in node_map:
                # Get Geometry
                x1, y1 = node_map[start_node_id]
                x2, y2 = node_map[end_node_id]
                L = np.sqrt((x2-x1)**2 + (y2-y1)**2)
                
                # Calculate Stiffness
                E_ksf = el['E'] * 144.0 
                I_ft4 = el['I'] / (12.0**4)
                A_ft2 = el['A'] / 144.0
                EI_val = E_ksf * I_ft4
                EA_val = E_ksf * A_ft2
                
                # Check for Point Loads on this member
                member_point_loads = [l for l in st.session_state["loads"] 
                                     if l['element_id'] == user_id and l['type'] == 'point']
                
                if not member_point_loads:
                    # No point loads? Just add the element normally.
                    ss.add_element(location=[[x1, y1], [x2, y2]], EI=EI_val, EA=EA_val)
                    member_map[user_id] = [current_ana_id]
                    current_ana_id += 1
                else:
                    # HAS POINT LOADS - We must split the element!
                    # For simplicity in this basic tool, we handle the FIRST point load found.
                    # (Handling multiple point loads on one beam requires sorting them by distance)
                    
                    pload = member_point_loads[0]
                    d = pload['location']
                    
                    # Validate distance
                    if d <= 0 or d >= L:
                        # Fallback if location is invalid
                        ss.add_element(location=[[x1, y1], [x2, y2]], EI=EI_val, EA=EA_val)
                        member_map[user_id] = [current_ana_id]
                        current_ana_id += 1
                        st.error(f"Load on Member {user_id} is outside the beam length ({L:.2f} ft).")
                    else:
                        # Math: Calculate split coordinate
                        ratio = d / L
                        x_mid = x1 + ratio * (x2 - x1)
                        y_mid = y1 + ratio * (y2 - y1)
                        
                        # Add Segment 1 (Start -> Load Point)
                        ss.add_element(location=[[x1, y1], [x_mid, y_mid]], EI=EI_val, EA=EA_val)
                        seg1_id = current_ana_id
                        current_ana_id += 1
                        
                        # Add Segment 2 (Load Point -> End)
                        ss.add_element(location=[[x_mid, y_mid], [x2, y2]], EI=EI_val, EA=EA_val)
                        seg2_id = current_ana_id
                        current_ana_id += 1
                        
                        # Map user member to BOTH segments (for distributed loads)
                        member_map[user_id] = [seg1_id, seg2_id]
                        
                        # Apply the Point Load to the NEW Node (the one between segments)
                        # The node ID of the split point is usually the latest node added.
                        # Anastruct internal node IDs are sequential.
                        # To be safe, we use the known connection. Segment 1 ends at the new node.
                        # ss.element_map[seg1_id].node_id2 is the split node.
                        split_node_id = ss.element_map[seg1_id].node_id2
                        ss.point_load(node_id=split_node_id, Fy=pload['value'])

        # 2. Add Supports
        for nid, stype in support_data:
            # We must be careful. User Node IDs are 1, 2... 
            # Anastruct Node IDs usually match if we added them in order, but splitting creates new nodes.
            # However, Anastruct's `add_support` works by finding the node at that coordinate
            # OR by ID. Let's map User IDs to coordinates to be safe.
            
            # Find the anastruct node ID that exists at this coordinate
            tgt_x, tgt_y = node_map[nid]
            # Simple search for the node ID at these coordinates
            found_node = ss.find_node_id(location=[tgt_x, tgt_y])
            
            if found_node:
                if stype == "fixed": ss.add_support_fixed(found_node)
                elif stype == "pinned": ss.add_support_hinged(found_node)
                elif stype == "roller": ss.add_support_roll(found_node)

        # 3. Apply Distributed Loads
        for l in st.session_state["loads"]:
            if l['type'] == 'distributed':
                # Apply to ALL segments of the member (in case it was split)
                target_segments = member_map.get(l['element_id'], [])
                for seg_id in target_segments:
                    ss.q_load(element_id=seg_id, q=l['value'])

        try:
            ss.solve()
            
            # TABS
            t1, t2, t3, t4 = st.tabs(["Structure", "Moment (M)", "Shear (V)", "Deflection (δ)"])
            
            with t1:
                

[Image of structural diagram]

                st.pyplot(ss.show_structure(show=False))
                st.caption("Structure with Loads (Split nodes indicate point loads)")
                
            with t2:
                st.write("### Bending Moment Diagram (k-ft)")
                st.pyplot(ss.show_bending_moment(show=False))
                
            with t3:
                st.write("### Shear Force Diagram (kips)")
                st.pyplot(ss.show_shear_force(show=False))
                
            with t4:
                st.write("### Displacement")
                st.warning("Graph shows displacement in **FEET**. Multiply by 12 for inches.")
                st.pyplot(ss.show_displacement(show=False))
                
            # REACTION TABLE
            st.divider()
            st.subheader("Reaction Forces")
            reactions = ss.get_node_results_system(node_id=0)
            
            rxn_list = []
            for node_result in reactions:
                nid = node_result['id']
                # Only show reactions if it's a support node
                # We check if this node ID corresponds to a coordinate where a user placed a support
                node_loc = ss.nodes_range[nid] if nid in ss.nodes_range else None
                
                is_support = False
                if node_loc:
                    # Check against user defined support coordinates
                    for user_nid, _ in support_data:
                         ux, uy = node_map[user_nid]
                         # Floating point comparison
                         if abs(ux - node_loc[0]) < 0.01 and abs(uy - node_loc[1]) < 0.01:
                             is_support = True
                             break
                
                if is_support:
                    rxn_list.append({
                        "Node ID (Solver)": nid,
                        "Fx (k)": round(node_result['Fx'], 2),
                        "Fy (k)": round(node_result['Fy'], 2),
                        "Moment (k-ft)": round(node_result['Ty'], 2)
                    })
            
            if rxn_list:
                st.table(pd.DataFrame(rxn_list))
            else:
                st.write("No supports defined.")

        except Exception as e:
            st.error(f"Analysis Error: {e}")
            st.write("Details:", e)
