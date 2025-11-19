import streamlit as st
import pandas as pd
from anastruct import SystemElements
import matplotlib.pyplot as plt

# 1. Setup Page
st.set_page_config(page_title="Structural Analysis Tool", layout="wide")
st.title("Structural Analysis Tool v2.0")

# Initialize Session State for Elements if not present
if "elements" not in st.session_state:
    st.session_state["elements"] = []

col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Build Structure")
    
    # --- NODES ---
    st.subheader("A. Nodes")
    if "nodes" not in st.session_state:
        st.session_state["nodes"] = pd.DataFrame([
            {"node_id": 1, "x": 0.0, "y": 0.0},
            {"node_id": 2, "x": 5.0, "y": 0.0},
        ])
    
    st.caption("Edit coordinates below. Add new rows for more nodes.")
    edited_nodes = st.data_editor(st.session_state["nodes"], num_rows="dynamic", hide_index=True)
    
    # --- MEMBERS ---
    st.subheader("B. Members")
    node_ids = edited_nodes["node_id"].tolist()
    
    with st.form("add_element"):
        c1, c2 = st.columns(2)
        start_node = c1.selectbox("Start Node", node_ids)
        end_node = c2.selectbox("End Node", node_ids, index=min(1, len(node_ids)-1))
        add_elem = st.form_submit_button("Add Member")
        
        if add_elem:
            if start_node != end_node:
                st.session_state["elements"].append((start_node, end_node))
            else:
                st.error("Start and End nodes cannot be the same.")

    # Display current elements with a delete option
    if st.session_state["elements"]:
        st.write("Current Members:")
        # Create a simple dataframe for display
        elem_df = pd.DataFrame(st.session_state["elements"], columns=["Start Node", "End Node"])
        st.dataframe(elem_df, hide_index=True)
        
        if st.button("Clear All Members"):
            st.session_state["elements"] = []
    
    # --- SUPPORTS ---
    st.subheader("C. Supports")
    support_data = []
    for nid in node_ids:
        # Create a row of checkboxes for each node
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        c1.write(f"Node {nid}")
        fixed = c2.checkbox("Fixed", key=f"fix_{nid}")
        pinned = c3.checkbox("Pin", key=f"pin_{nid}")
        roller = c4.checkbox("Roll", key=f"roll_{nid}")
        
        if fixed: support_data.append((nid, "fixed"))
        elif pinned: support_data.append((nid, "pinned"))
        elif roller: support_data.append((nid, "roller"))

    # --- LOADS ---
    st.subheader("D. Loads")
    # Initialize loads in session state
    if "loads" not in st.session_state:
        st.session_state["loads"] = []

    with st.form("add_load"):
        load_type = st.selectbox("Load Type", ["Point Load", "Distributed Load"])
        
        # Dynamic form inputs based on load type
        element_indices = range(len(st.session_state["elements"]))
        element_labels = [f"Member {i+1} (Node {s}->{e})" for i, (s, e) in enumerate(st.session_state["elements"])]
        
        selected_elem_idx = st.selectbox("Apply to Member", element_indices, format_func=lambda x: element_labels[x]) if element_indices else None
        
        val = st.number_input("Magnitude (kN or kN/m)", value=-10.0)
        
        submit_load = st.form_submit_button("Add Load")
        if submit_load and selected_elem_idx is not None:
            # Store load as a dict
            # element_id in anastruct is 1-based, so we use selected_elem_idx + 1
            st.session_state["loads"].append({
                "type": load_type,
                "element_id": selected_elem_idx + 1,
                "value": val
            })

    # Show active loads
    if st.session_state["loads"]:
        st.write("Active Loads:")
        st.table(pd.DataFrame(st.session_state["loads"]))
        if st.button("Clear Loads"):
            st.session_state["loads"] = []

with col2:
    st.header("2. Results")
    
    if not st.session_state["elements"]:
        st.info("Please define nodes and members first.")
    else:
        ss = SystemElements()
        
        # 1. Add Elements
        node_map = {row['node_id']: [row['x'], row['y']] for i, row in edited_nodes.iterrows()}
        for start, end in st.session_state["elements"]:
            if start in node_map and end in node_map:
                ss.add_element(location=[node_map[start], node_map[end]])

        # 2. Add Supports
        for node_id, sup_type in support_data:
            if sup_type == "fixed":
                ss.add_support_fixed(node_id=node_id)
            elif sup_type == "pinned":
                ss.add_support_hinged(node_id=node_id)
            elif sup_type == "roller":
                ss.add_support_roll(node_id=node_id)

        # 3. Add Loads
        for load in st.session_state["loads"]:
            if load["type"] == "Point Load":
                # Point load at center of element for simplicity in this version
                ss.point_load(node_id=None, element_id=load["element_id"], Fy=load["value"]) 
                # Note: For more precise location, we'd need an extra input for 'location ratio'
            elif load["type"] == "Distributed Load":
                ss.q_load(q=load["value"], element_id=load["element_id"])

        # 4. Solve
        try:
            ss.solve()
            
            # Tabs for different views
            tab1, tab2, tab3, tab4 = st.tabs(["Structure", "Bending Moment", "Shear Force", "Deflection"])
            
            with tab1:
                st.write("**Structural Geometry & Reactions**")
                st.pyplot(ss.show_structure(show=False))
            with tab2:
                st.write("**Bending Moment Diagram**")
                st.pyplot(ss.show_bending_moment(show=False))
            with tab3:
                st.write("**Shear Force Diagram**")
                st.pyplot(ss.show_shear_force(show=False))
            with tab4:
                st.write("**Displacement**")
                st.pyplot(ss.show_displacement(show=False))
                
        except Exception as e:
            st.error(f"Analysis failed. Structure might be unstable or missing supports.\nError details: {e}")
