# -*- coding: utf-8 -*-
import sys

if __name__ == '__main__':
    if sys.argv[-1] == 'get_password':
        from lib import main
        main.getPassword()
    elif sys.argv[-1] == 'export_remove_all':
        from lib import main
        main.removeExported()
    elif sys.argv[-1] == 'export_refresh':
        from lib import main
        main.refreshExported()
    elif sys.argv[-1] == 'export':
        from lib import export
        export.export(category=sys.argv[-2])
    else:
        from lib import main
        main.main()