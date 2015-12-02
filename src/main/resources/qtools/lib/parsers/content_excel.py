"""
Reads the assays in Carolyn's Excel format

This is probably super brittle and needs to be more systematic,
or the entry needs to be controlled by a webpage... or software engineer.
"""
import csv, re, operator
from collections import defaultdict

from qtools.model.content import BGGeneInfo, BGDesign, BGFigures, BGAssayValidation

TABLE_NAME_RE = re.compile('Table Name\:\s+(\w+)')
ENSG_RE = re.compile('^ENSG\d+')

def get_assay_info(excel_csv_path):
    gene_infos = dict()

    with open(excel_csv_path, 'rb') as csvfile:
        dialect = csv.Sniffer().sniff(csvfile.read(4096))
        csvfile.seek(0)
        reader = csv.reader(csvfile, dialect)
        indices = get_column_indices(reader) # this will advance the reader a few lines

        ensembl_col_num = indices[BGGeneInfo]['ensembl_gene']
        for line in reader:
            if ENSG_RE.match(line[ensembl_col_num]):
                ensembl_id = line[ensembl_col_num].strip()
                if ensembl_id not in gene_infos:
                    gene_info = BGGeneInfo()
                    for attr, idx in indices[BGGeneInfo].items():
                        if line[idx]:
                            setattr(gene_info, attr, line[idx])
                    gene_infos[ensembl_id] = gene_info
                else:
                    gene_info = gene_infos[ensembl_id]

                design_attrs = [line[idx] for col, idx in indices[BGDesign].items()]
                if any(design_attrs):
                    design = BGDesign()
                    for attr, idx in indices[BGDesign].items():
                        if line[idx]:
                            setattr(design, attr, line[idx])

                        figure_attrs = [line[idx] for col, idx in indices[BGFigures].items()]
                        if any(figure_attrs):
                            figure = BGFigures()
                            for attr, idx in indices[BGFigures].items():
                                if line[idx]:
                                    setattr(figure, attr, line[idx])
                            design.figures.append(figure)

                        validation_attrs = [line[idx] for col, idx in indices[BGAssayValidation].items()]
                        if any(validation_attrs):
                            validation = BGAssayValidation()
                            for attr, idx in indices[BGAssayValidation].items():
                                if line[idx]:
                                    setattr(validation, attr, line[idx])
                            design.validations.append(validation)

                    gene_info.designs.append(design)

    return sorted(gene_infos.values(), key=operator.attrgetter('ensembl_gene'))


def get_column_indices(csv_reader):
    """

    :param csv_fh: File handle to open CSV file
    :return: the indices of each column
    """
    table_name_map = {'GeneInfo': BGGeneInfo,
                      'Assay': BGDesign,
                      'AssayFigures': BGFigures,
                      'AssayValidation': BGAssayValidation}

    line = True
    index_map = defaultdict(dict)
    boundary_map = dict()
    while(line):
        line = csv_reader.next()
        table_names = [(idx, col) for idx, col in enumerate(line) if TABLE_NAME_RE.match(col)]
        if table_names:
            for idx, (cidx, col) in enumerate(sorted(table_names)):
                match = TABLE_NAME_RE.match(col)
                if idx == len(table_names)-1:
                    therange = xrange(cidx,len(line))
                else:
                    therange = xrange(cidx,table_names[idx+1][0])
                boundary_map[table_name_map[match.group(1)]] = therange
            break

    while(line):
        line = csv_reader.next()
        if 'ensembl_gene' in line and 'design_id' in line:
            # these are the indices
            for entity, therange in boundary_map.items():
                for idx in therange:
                    if line[idx] in entity.__table__.columns:
                        index_map[entity][line[idx]] = idx
            break

    return index_map
