"""
import tempfile

from autorad.utils.sample_datasets import load_mednist_dataset

root_dir = tempfile.mkdtemp()
dataset = load_mednist_dataset(root_dir)
dataset.dataframe()
"""
