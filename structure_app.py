import streamlit as st
import pandas as pd
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
        {"node_id": 2, "x": 10.0, "y": 0.0}, # Default 10 ft span
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
        
        # Default: Steel (E=29000 ksi), W12x26 (approx I=200, A=7.6)
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
        # Display formatted table
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
        
        # Default load: 1 kip or 1 k/ft
        mag = c2.number_input("Magnitude (k or k/ft)", value=-1.0)
        st.caption("Negative = Downward Direction")
        
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
        
        # --- SOLVER UNIT CONVERSION LOGIC ---
        # We convert EVERYTHING to FEET and KIPS for the solver.
        # This ensures the Moment Diagram is in k-ft and Length is in ft.
        
        for el in st.session_state["elements"]:
            start, end = el['start'], el['end']
            if start in node_map and end in node_map:
                
                # CONVERSION:
                # E input is ksi. Convert to ksf (kips/ft^2) -> E * 144
                E_ksf = el['E'] * 144.0 
                
                # I input is in^4. Convert to ft^4 -> I / 12^4
                I_ft4 = el['I'] / (12.0**4)
                
                # A input is in^2. Convert to ft^2 -> A / 144
                A_ft2 = el['A'] / 144.0
                
                # Calculate Stiffness factors
                EI_val = E_ksf * I_ft4
                EA_val = E_ksf * A_ft2
                
                ss.add_element(
                    location=[node_map[start], node_map[end]],
                    EI=EI_val,
                    EA=EA_val
                )

        # Add Supports
        for nid, stype in support_data:
            if stype == "fixed": ss.add_support_fixed(nid)
            elif stype == "pinned": ss.add_support_hinged(nid)
            elif stype == "roller": ss.add_support_roll(nid)

        # Add Loads
        for l in st.session_state["loads"]:
            if l['type'] == "point":
                # Point load location is already in feet. Value is in kips. No conversion needed.
                ss.point_load(element_id=l['element_id'], Fy=l['value'], location=l['location'])
            else:
                # Distributed load is k/ft. No conversion needed.
                ss.q_load(element_id=l['element_id'], q=l['value'])

        try:
            ss.solve()
            
            # TABS
            t1, t2, t3, t4 = st.tabs(["Structure", "Moment (M)", "Shear (V)", "Deflection (δ)"])
            
            with t1:
                st.pyplot(ss.show_structure(show=False))
                st.caption("Dimensions in Feet.")
                
            with t2:
                st.write("### Bending Moment Diagram (k-ft)")
                st.pyplot(ss.show_bending_moment(show=False))
                
            with t3:
                st.write("### Shear Force Diagram (kips)")
                st.pyplot(ss.show_shear_force(show=False))
                
            with t4:
                st.write("### Displacement")
                st.warning("Note: The graph below shows displacement in **FEET** (because the model is built in feet). Multiply by 12 to get inches.")
                st.pyplot(ss.show_displacement(show=False))
                
            # REACTION TABLE
            st.divider()
            st.subheader("Reaction Forces")
            reactions = ss.get_node_results_system(node_id=0) # 0 gets all
            
            # Parse reactions into a clean table
            rxn_list = []
            for node_result in reactions:
                nid = node_result['id']
                # Check if this node actually has a support to avoid listing 0s for free nodes
                is_supported = any(s[0] == nid for s in support_data)
                if is_supported:
                    rxn_list.append({
                        "Node": nid,
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
