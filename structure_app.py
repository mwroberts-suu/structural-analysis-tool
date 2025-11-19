import streamlit as st
import pandas as pd
from anastruct import SystemElements
import matplotlib.pyplot as plt

# 1. Setup Page
st.set_page_config(page_title="Simple Beam Analyzer", layout="wide")
st.title("Student Structural Analysis Tool")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Define Geometry")
    
    # Initialize default nodes if not in session state
    if "nodes" not in st.session_state:
        st.session_state["nodes"] = pd.DataFrame([
            {"node_id": 1, "x": 0.0, "y": 0.0},
            {"node_id": 2, "x": 5.0, "y": 0.0},
        ])

    # Editable Table for Nodes
    st.write("Edit Node Coordinates:")
    edited_nodes = st.data_editor(st.session_state["nodes"], num_rows="dynamic")
    
    st.subheader("2. Define Connections")
    # Create a list of possible connections based on nodes
    node_ids = edited_nodes["node_id"].tolist()
    
    # Simple Element Creator (Connect Node A to Node B)
    with st.form("add_element"):
        c1, c2 = st.columns(2)
        start_node = c1.selectbox("Start Node", node_ids)
        end_node = c2.selectbox("End Node", node_ids, index=len(node_ids)-1)
        add_elem = st.form_submit_button("Add Element")
        
        if "elements" not in st.session_state:
            st.session_state["elements"] = []
            
        if add_elem:
            st.session_state["elements"].append((start_node, end_node))

    # Show current elements
    st.write("Current Elements:", st.session_state["elements"])
    
    if st.button("Clear All Elements"):
        st.session_state["elements"] = []

with col2:
    st.subheader("3. Visualization & Results")
    
    # Build the Structure Model
    ss = SystemElements()
    
    # Add Nodes/Elements from our inputs to anastruct
    # Note: anastruct creates elements by coordinate, so we map IDs to coords
    node_map = {row['node_id']: [row['x'], row['y']] for i, row in edited_nodes.iterrows()}
    
    for start, end in st.session_state["elements"]:
        if start in node_map and end in node_map:
            ss.add_element(location=[node_map[start], node_map[end]])
    
    # Add some default supports for demo purposes (Pin at first node, Roller at last)
    if len(node_map) >= 2:
        first_node = edited_nodes.iloc[0]['node_id']
        last_node = edited_nodes.iloc[-1]['node_id']
        ss.add_support_hinged(node_id=first_node)
        ss.add_support_roll(node_id=last_node)
        
        # Add a default load for demo
        ss.q_load(q=-10, element_id=1)
        ss.solve()
        
        # Plotting using Matplotlib (anastruct returns a fig)
        fig = ss.show_structure(show=False)
        st.pyplot(fig)
        
        st.success("Model Solved! Showing Geometry above.")
        
        with st.expander("View Analysis Diagrams"):
            st.write("**Bending Moment**")
            st.pyplot(ss.show_bending_moment(show=False))
            st.write("**Deflection**")
            st.pyplot(ss.show_displacement(show=False))
