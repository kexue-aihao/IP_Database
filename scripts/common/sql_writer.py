"""
MySQL-compatible SQL dump writer.

Generates .sql files containing CREATE TABLE + batched INSERT + INDEX statements.
Each file is self-contained and can be imported independently.
"""

import os


BATCH_SIZE = 500  # rows per INSERT statement


class SQLWriter:
    """Writes a single SQL table dump file."""

    def __init__(self, path, table_name, columns, comment='', engine='InnoDB'):
        """
        path       — output .sql file path
        table_name — MySQL table name
        columns    — list of (name, sql_type, comment) tuples
        comment    — table comment
        """
        self.path = path
        self.table_name = table_name
        self.columns = columns
        self.comment = comment
        self.engine = engine
        self._f = None
        self._batch = []         # accumulated value tuples
        self._row_count = 0
        self._header_written = False

    def _ensure_header(self):
        if self._header_written:
            return
        self._f = open(self.path, 'w', encoding='utf-8')

        # Separate data columns from constraints
        self._data_cols = []
        col_def_lines = []
        constraint_lines = []

        for name, sql_type, col_comment in self.columns:
            if name.upper() == 'PRIMARY KEY' or name.upper().startswith('KEY '):
                constraint_lines.append('  %s %s' % (name, sql_type))
                continue
            # Skip AUTO_INCREMENT columns from INSERT data (MySQL auto-generates)
            if 'AUTO_INCREMENT' in sql_type.upper():
                col_def_lines.append('  `%s` %s' % (name, sql_type))
            else:
                self._data_cols.append(name)
                comment_str = " COMMENT '%s'" % col_comment if col_comment else ''
                col_def_lines.append('  `%s` %s%s' % (name, sql_type, comment_str))

        # Assemble col defs: separate each with comma, add trailing comma if constraints follow
        all_col_defs = ',\n'.join(col_def_lines)
        if constraint_lines:
            all_col_defs += ','

        lines = [
            '-- =============================================================',
            '-- %s' % self.comment,
            '-- =============================================================',
            '',
            'SET NAMES utf8mb4;',
            '',
            'DROP TABLE IF EXISTS `%s`;' % self.table_name,
            'CREATE TABLE `%s` (' % self.table_name,
            all_col_defs,
        ] + constraint_lines + [
            ') ENGINE=%s DEFAULT CHARSET=utf8mb4%s;' % (
                self.engine,
                " COMMENT='%s'" % self.comment if self.comment else '',
            ),
            '',
        ]

        self._f.write('\n'.join(lines))
        self._header_written = True
        self._col_name_list = ', '.join('`%s`' % n for n in self._data_cols)

    def _escape(self, val):
        """Format a Python value as a SQL literal."""
        if val is None:
            return 'NULL'
        if isinstance(val, bool):
            return '1' if val else '0'
        if isinstance(val, int):
            return str(val)
        if isinstance(val, float):
            return '%.6f' % val
        s = str(val).replace('\\', '\\\\').replace("'", "\\'")
        return "'%s'" % s

    def add_row(self, values):
        """Add a row to the current batch. Flushes when batch is full."""
        self._ensure_header()
        self._batch.append(values)
        self._row_count += 1

        if len(self._batch) >= BATCH_SIZE:
            self._flush_batch()

    def _flush_batch(self):
        if not self._batch:
            return
        lines = [
            'INSERT INTO `%s` (%s) VALUES' % (self.table_name, self._col_name_list),
        ]
        for i, row in enumerate(self._batch):
            vals = ', '.join(self._escape(v) for v in row)
            prefix = '  (' if i == 0 else '  ,('
            lines.append(prefix + vals + ')')

        self._f.write('\n'.join(lines) + ';\n\n')
        self._batch = []

    def close(self):
        """Flush remaining rows and write footer."""
        self._ensure_header()
        self._flush_batch()

        # Write indexes
        indexes = self._build_indexes()
        if indexes:
            self._f.write('\n'.join(indexes) + '\n')

        self._f.close()
        return self._row_count

    def _build_indexes(self):
        """Generate CREATE INDEX statements based on column names."""
        idx_lines = []
        col_set = {c[0] for c in self.columns}

        if 'start_ip_int' in col_set:
            idx_lines.append('CREATE INDEX `idx_%s_start` ON `%s` (`start_ip_int`);' % (
                self.table_name, self.table_name))
            idx_lines.append('CREATE INDEX `idx_%s_end` ON `%s` (`end_ip_int`);' % (
                self.table_name, self.table_name))

        if 'start_ip_hex' in col_set:
            idx_lines.append('CREATE INDEX `idx_%s_hex_start` ON `%s` (`start_ip_hex`);' % (
                self.table_name, self.table_name))
            idx_lines.append('CREATE INDEX `idx_%s_hex_end` ON `%s` (`end_ip_hex`);' % (
                self.table_name, self.table_name))

        if 'province' in col_set:
            idx_lines.append('CREATE INDEX `idx_%s_province` ON `%s` (`province`);' % (
                self.table_name, self.table_name))

        if 'idc_vendor' in col_set:
            idx_lines.append('CREATE INDEX `idx_%s_idc` ON `%s` (`idc_vendor`);' % (
                self.table_name, self.table_name))

        return idx_lines


def write_idc_table(path, table_name, idc_ranges, ip_version=4, comment=''):
    """Write an IDC reference table .sql file.

    idc_ranges is a list of (vendor, start_ip, end_ip, start_int, end_int, region).
    """
    if ip_version == 4:
        columns = [
            ('id', 'INT(11) NOT NULL AUTO_INCREMENT', ''),
            ('vendor', 'VARCHAR(30) NOT NULL', '厂商名称'),
            ('start_ip', 'VARCHAR(15) NOT NULL', '起始IPv4'),
            ('end_ip', 'VARCHAR(15) NOT NULL', '结束IPv4'),
            ('start_ip_int', 'BIGINT(20) NOT NULL', '起始IP整型'),
            ('end_ip_int', 'BIGINT(20) NOT NULL', '结束IP整型'),
            ('region', "VARCHAR(30) NOT NULL DEFAULT ''", '主要区域'),
            ('PRIMARY KEY', '(id)', ''),
        ]
    else:
        columns = [
            ('id', 'INT(11) NOT NULL AUTO_INCREMENT', ''),
            ('vendor', 'VARCHAR(30) NOT NULL', '厂商名称'),
            ('start_ip', 'VARCHAR(39) NOT NULL', '起始IPv6'),
            ('end_ip', 'VARCHAR(39) NOT NULL', '结束IPv6'),
            ('start_ip_hex', "VARCHAR(32) NOT NULL DEFAULT ''", '起始IP十六进制'),
            ('end_ip_hex', "VARCHAR(32) NOT NULL DEFAULT ''", '结束IP十六进制'),
            ('region', "VARCHAR(30) NOT NULL DEFAULT ''", '主要区域'),
            ('PRIMARY KEY', '(id)', ''),
        ]

    writer = SQLWriter(path, table_name, columns, comment=comment)
    for row in idc_ranges:
        writer.add_row(row)
    count = writer.close()
    return count
