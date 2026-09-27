#!/bin/bash
#SBATCH --account=YOUR_PROJECT   # e.g. PAS1811
#SBATCH --job-name=s1p01_unload0
#SBATCH --output=%x.o%j       
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gpus=1
#SBATCH --time=00:20:00
#SBATCH --mail-type=ALL         

cd $SLURM_SUBMIT_DIR
#export OMP_NUM_THREADS=28
time ./Void_model.exe > MT_s1p01_unload0
