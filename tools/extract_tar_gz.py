import sys, tarfile, os

def main():
    if len(sys.argv) < 3:
        print("Usage: extract_tar_gz.py <input.tar.gz> <dest_dir>")
        return 2
    src = sys.argv[1]
    dst = sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    with tarfile.open(src, 'r:gz') as tf:
        tf.extractall(dst)
    print("EXTRACT_OK")
    return 0

if __name__ == '__main__':
    sys.exit(main())
