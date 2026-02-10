"""Script to create sample iLab export files for testing and demos."""

import pandas as pd
from pathlib import Path

# Get the fixtures directory
fixtures_dir = Path(__file__).parent

# Create Equipment sample
equipment_data = {
    'Service Name': [
        'Confocal Microscope LSM 880',
        'Flow Cytometer BD FACS Aria III',
        'Mass Spectrometer Orbitrap Fusion',
        'Electron Microscope TEM 120kV',
        'NMR Spectrometer 600MHz'
    ],
    'Core': [
        'Microscopy Core',
        'Flow Cytometry Core',
        'Proteomics Core',
        'Electron Microscopy Core',
        'NMR Core'
    ],
    'PI': [
        'Dr. Alice Smith',
        'Dr. Bob Jones',
        'Dr. Carol Williams',
        'Dr. David Brown',
        'Dr. Emily Davis'
    ],
    'Location': [
        'Biology Building, Room 101',
        'Medical Sciences, Room 205',
        'Chemistry Building, Room 310',
        'Materials Science, Room 150',
        'Chemistry Building, Room 220'
    ],
    'Equipment ID': [
        'EQ-001',
        'EQ-002',
        'EQ-003',
        'EQ-004',
        'EQ-005'
    ],
    'Description': [
        'Advanced confocal imaging with spectral detection',
        'High-speed cell sorting and multicolor analysis',
        'High-resolution protein mass spectrometry',
        'Transmission electron microscopy for nano-scale imaging',
        'High-field NMR for structural analysis'
    ]
}

equipment_df = pd.DataFrame(equipment_data)

# Save as both CSV and Excel
equipment_df.to_csv(fixtures_dir / 'ilab_equipment_sample.csv', index=False)
equipment_df.to_excel(fixtures_dir / 'ilab_equipment_sample.xlsx', index=False, engine='openpyxl')

print(f"✓ Created {fixtures_dir / 'ilab_equipment_sample.csv'}")
print(f"✓ Created {fixtures_dir / 'ilab_equipment_sample.xlsx'}")

# Create Services sample
services_data = {
    'Service Name': [
        'Confocal Microscopy Training',
        'Flow Cytometry Analysis',
        'Mass Spectrometry Run',
        'Sample Preparation - Proteomics',
        'NMR Spectroscopy Analysis'
    ],
    'Core': [
        'Microscopy Core',
        'Flow Cytometry Core',
        'Proteomics Core',
        'Proteomics Core',
        'NMR Core'
    ],
    'Rate Per Hour': [50, 75, 100, 60, 85],
    'Service ID': [
        'SVC-001',
        'SVC-002',
        'SVC-003',
        'SVC-004',
        'SVC-005'
    ],
    'Active': ['Yes', 'Yes', 'Yes', 'Yes', 'No']
}

services_df = pd.DataFrame(services_data)
services_df.to_csv(fixtures_dir / 'ilab_services_sample.csv', index=False)
services_df.to_excel(fixtures_dir / 'ilab_services_sample.xlsx', index=False, engine='openpyxl')

print(f"✓ Created {fixtures_dir / 'ilab_services_sample.csv'}")
print(f"✓ Created {fixtures_dir / 'ilab_services_sample.xlsx'}")

# Create PI Directory sample
pi_data = {
    'PI Name': [
        'Dr. Alice Smith',
        'Dr. Bob Jones',
        'Dr. Carol Williams',
        'Dr. David Brown',
        'Dr. Emily Davis',
        'Dr. Frank Miller',
        'Dr. Grace Wilson'
    ],
    'Email': [
        'alice.smith@university.edu',
        'bob.jones@university.edu',
        'carol.williams@university.edu',
        'david.brown@university.edu',
        'emily.davis@university.edu',
        'frank.miller@university.edu',
        'grace.wilson@university.edu'
    ],
    'Department': [
        'Biology',
        'Molecular Medicine',
        'Chemistry',
        'Materials Science',
        'Chemistry',
        'Neuroscience',
        'Immunology'
    ],
    'Lab': [
        'Smith Lab - Cell Biology',
        'Jones Lab - Cancer Research',
        'Williams Lab - Protein Chemistry',
        'Brown Lab - Nanomaterials',
        'Davis Lab - Structural Chemistry',
        'Miller Lab - Systems Neuroscience',
        'Wilson Lab - Adaptive Immunity'
    ],
    'Phone': [
        '555-0101',
        '555-0102',
        '555-0103',
        '555-0104',
        '555-0105',
        '555-0106',
        '555-0107'
    ],
    'Office': [
        'Biology 101',
        'Medical Sciences 205',
        'Chemistry 310',
        'Materials Science 150',
        'Chemistry 220',
        'Neuroscience 412',
        'Immunology 305'
    ]
}

pi_df = pd.DataFrame(pi_data)
pi_df.to_csv(fixtures_dir / 'ilab_pi_directory_sample.csv', index=False)
pi_df.to_excel(fixtures_dir / 'ilab_pi_directory_sample.xlsx', index=False, engine='openpyxl')

print(f"✓ Created {fixtures_dir / 'ilab_pi_directory_sample.csv'}")
print(f"✓ Created {fixtures_dir / 'ilab_pi_directory_sample.xlsx'}")

print("\n✅ All sample iLab files created successfully!")
