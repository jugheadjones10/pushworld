#!/usr/bin/env python3
"""
Script to distribute puzzles from original folder to train, test, and archive folders.
"""

import argparse
import os
import random
import shutil
from pathlib import Path
from typing import Dict, List, Optional


def list_puzzle_files(directory: str) -> List[str]:
    """Get all puzzle files (.pwp) from a directory.

    Args:
        directory: Path to the directory containing puzzle files

    Returns:
        List of puzzle filenames
    """
    puzzle_dir = Path(directory)
    if not puzzle_dir.exists():
        return []

    return [f.name for f in puzzle_dir.glob("*.pwp")]


def shuffle_puzzles(
    base_dir: str,
    train_percent: float = 0.7,
    test_percent: float = 0.2,
    archive_percent: float = 0.1,
    seed: Optional[int] = None,
) -> Dict[str, int]:
    """Distribute puzzles from original folder to train, test, and archive folders.

    Args:
        base_dir: Base directory containing the puzzle folders
        train_percent: Percentage of puzzles to put in train folder
        test_percent: Percentage of puzzles to put in test folder
        archive_percent: Percentage of puzzles to put in archive folder
        seed: Random seed for reproducibility

    Returns:
        Dictionary with counts of puzzles in each folder
    """
    if seed is not None:
        random.seed(seed)

    # Normalize percentages
    total = train_percent + test_percent + archive_percent
    if total != 1.0:
        print(f"Warning: Percentages sum to {total}, normalizing to 100%")
        train_percent = train_percent / total
        test_percent = test_percent / total
        archive_percent = archive_percent / total

    # Folder paths
    original_dir = os.path.join(base_dir, "original")
    train_dir = os.path.join(base_dir, "train")
    test_dir = os.path.join(base_dir, "test")
    archive_dir = os.path.join(base_dir, "archive")

    # Clear the target directories first
    for directory in [train_dir, test_dir, archive_dir]:
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            if os.path.isfile(file_path) and file.endswith(".pwp"):
                os.remove(file_path)

    # Get all puzzle files from original directory
    puzzle_files = list_puzzle_files(original_dir)

    if not puzzle_files:
        print("No puzzle files found in original directory")
        return {"train": 0, "test": 0, "archive": 0}

    # Shuffle files
    random.shuffle(puzzle_files)

    # Calculate split points
    total_files = len(puzzle_files)
    train_count = int(total_files * train_percent)
    test_count = int(total_files * test_percent)

    # Split the files
    train_subset = puzzle_files[:train_count]
    test_subset = puzzle_files[train_count : train_count + test_count]
    archive_subset = puzzle_files[train_count + test_count :]

    # Copy files to their destination folders
    for filename in train_subset:
        shutil.copy2(
            os.path.join(original_dir, filename), os.path.join(train_dir, filename)
        )

    for filename in test_subset:
        shutil.copy2(
            os.path.join(original_dir, filename), os.path.join(test_dir, filename)
        )

    for filename in archive_subset:
        shutil.copy2(
            os.path.join(original_dir, filename), os.path.join(archive_dir, filename)
        )

    result = {
        "train": len(train_subset),
        "test": len(test_subset),
        "archive": len(archive_subset),
    }

    print(
        f"Distribution complete: {result['train']} in train, {result['test']} in test, {result['archive']} in archive"
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Distribute puzzles from original folder to train, test, and archive folders"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default="/Users/kimyoungjin/Projects/monkey/pushworld/python3/src/pushworld/braindead",
        help="Base directory containing the puzzle folders (default: python3/src/pushworld/braindead)",
    )
    parser.add_argument(
        "--train",
        type=float,
        default=0.49,
        help="Percentage for train set (default: 70.0)",
    )
    parser.add_argument(
        "--test",
        type=float,
        default=0.01,
        help="Percentage for test set (default: 20.0)",
    )
    parser.add_argument(
        "--archive",
        type=float,
        default=0.5,
        help="Percentage for archive (default: 10.0)",
    )
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")

    args = parser.parse_args()

    shuffle_puzzles(
        base_dir=args.base_dir,
        train_percent=args.train,
        test_percent=args.test,
        archive_percent=args.archive,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
