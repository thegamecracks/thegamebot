import itertools
import os


def rawincount(filename):
    """Returns the number of lines in a file.

    Citation needed.

    """
    with open(filename, 'rb') as f:
        bufgen = itertools.takewhile(lambda x: x, (f.raw.read(1024*1024)
                                         for _ in itertools.repeat(None)))
        return sum( buf.count(b'\n') for buf in bufgen ) + 1


def rename_enumerate(src, dst, **kwargs):
    """Rename a file and automatically enumerate the filename
    if a current file exists with that name:
    foo.bar.bak
    foo1.bar.bak
    foo2.bar.bak
    ...

    Note that this will also skip names used by directories even when
    given a file, and vice versa.

    """
    if not os.path.exists(dst):
        return os.rename(src, dst, **kwargs)

    root, exts = splitext_all(dst)
    ext = ''.join(exts)

    n = 1
    while os.path.exists(dst_new := f'{root}{n}{ext}'):
        n += 1

    return os.rename(src, dst_new, **kwargs)


def splitext_all(path):
    """Like os.path.splitext except this returns all extensions
    instead of just one.

    Returns:
        Tuple[str, List[str]]: root + ''.join(exts) == path

    """
    root, ext = os.path.splitext(path)

    extensions = [ext]
    root_new, ext = os.path.splitext(root)
    while ext:
        extensions.append(ext)
        root = root_new
        root_new, ext = os.path.splitext(root)
    return root, extensions[::-1]
