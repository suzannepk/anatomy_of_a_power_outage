#!/bin/bash
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --time=20
#SBATCH --ntasks-per-node=128
#SBATCH --job-name test_mpi-%j
#SBATCH -o outage_mpi-%j.out
#SBATCH -e outage_mpi-%j.err

cd /global/cfs/cdirs/m4388/2025_BootCamp_ORNL/anatomy_of_a_power_outage/

module load conda
conda activate /global/cfs/cdirs/m4388/2025_BootCamp_ORNL/anatomy_of_a_power_outage/env/suz_bootcamp

srun -n 16  python GenerateOutageCSV.py 2014 2015 2016 2017 2018 2019 1.0
srun -n 16 python GenerateOutageCSV.py 2020 2021 1.0
