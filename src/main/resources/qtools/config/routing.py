"""Routes configuration

The more specific and detailed routes should be defined first so they
may take precedent over the more generic routes. For more information
refer to the routes manual at http://routes.groovie.org/docs/
"""
from routes import Mapper

def make_map(config):
    """Create, configure and return the routes Mapper"""
    map = Mapper(directory=config['pylons.paths']['controllers'],
                 always_scan=config['debug'])
    map.minimization = False
    map.explicit = False

    # The ErrorController route (handles 404/500 error pages); it should
    # likely stay at the top, ensuring it can always be resolved
    map.connect('/error/{action}', controller='error')
    map.connect('/error/{action}/{id}', controller='error')

    # CUSTOM ROUTES HERE

    map.connect('/', controller='home', action='index')
    # TODO: how to do this the right way?
    map.connect('/stats', controller='stats', action='index')
    map.connect('/stats/', controller='stats', action='index')

    map.connect('/metrics', controller='metrics', action='index')
    map.connect('/metrics/', controller='metrics', action='index')

    map.connect('/external', controller='external', action='index')
    map.connect('/external/', controller='external', action='index')

    map.connect('/product/consumable', controller='consumable', action='list')
    map.connect('/product/consumable/', controller='consumable', action='list')
    
    map.connect('/product/consumable/{action}', controller='consumable')
    map.connect('/product/consumable/{action}/{id}', controller='consumable')

    for method in ('new', 'create', 'edit', 'save', 'delete', 'editplate', 'saveplate',
                   'list', 'plates', 'plate_template', 'plate_template_download', 'plate_upload', 'plate_do_upload', 'csfv_unhook'):
        map.connect('/product/batch/%s' % method, controller='product', action='batch_%s' % method)
        map.connect('/product/batch/%s/{id}' % method, controller='product', action='batch_%s' % method)

    for method in ('list','new', 'create', 'edit', 'save', 'delete', 'plates'):
        map.connect('/product/groove/%s' % method, controller='groove')
        map.connect('/product/groove/%s/{id}' % method, controller='groove')

    map.connect('/product', controller='product', action='index')
    map.connect('/product/', controller='product', action='index')

    map.connect('/metrics/history_csv/{box_code}/{plate_type}', controller='metrics', action='history_csv', reprocess_config_id='')
    map.connect('/metrics/{action}/{id}', controller='metrics', mode='group', reprocess_config_id=None)
    map.connect('/metrics/{action}/{id}/', controller='metrics', mode='group', reprocess_config_id=None)
    map.connect('/metrics/{action}/{id}/{reprocess_config_id}', mode='group', controller='metrics')
    map.connect('/drmetrics/{action}/{id}', controller='metrics', mode='dr', reprocess_config_id='')
    map.connect('/platemetrics/{action}/{id}', controller='metrics', mode='plate', reprocess_config_id='')
    map.connect('/platemetrics/{action}/{id}/{reprocess_config_id}', controller='metrics', mode='plate')
    map.connect('/statsmetrics/{action}/{id}', controller='metrics', mode='plate_non_cert', reprocess_config_id='')
    map.connect('/statsmetrics/{action}/{id}/{reprocess_config_id}', controller='metrics', mode='plate_non_cert')
    map.connect('/metrics/history/{box_code}/{plate_type}/{plate_order}', controller='metrics', action='history', mode='plate', reprocess_config_id='')
    
    #map.connect('/metrics/wells/{id}', controller='metrics', action='wells', reprocess_config_id=None)
    #map.connect('/metrics/wells/{id}/{reprocess_config_id}', controller='metrics', action='wells')
    
    map.connect('/stats/boxes/day/{year}/{month}/{day}', controller='stats', action='boxes_by_day')
    map.connect('/stats/boxes', controller='stats', action='boxes_by_week', weeks_ago=0)
    map.connect('/stats/boxes/week/{weeks_ago}', controller='stats', action='boxes_by_week', requirements={'weeks_ago': '\d+'})
    
    map.connect('/stats/operators/day/{year}/{month}/{day}', controller='stats', action='operators_by_day')
    map.connect('/stats/operators', controller='stats', action='operators_by_week', weeks_ago=0)
    map.connect('/stats/operators/week/{weeks_ago}', controller='stats', action='operators_by_week', requirements={'weeks_ago': '\d+'})

    # TODO clean this up with submappers
    map.connect('/status/readers', controller='admin', action='readers', admin=False)
    map.connect('/admin/readers', controller='admin', action='readers', admin=True)
    map.connect('/status/colorcomp', controller='admin', action='colorcomp', admin=False)
    map.connect('/admin/colorcomp', controller='admin', action='colorcomp', admin=True)
    map.connect('/status/readers/prod', controller='admin', action='prod', admin=False)
    map.connect('/admin/readers/prod', controller='admin', action='prod', admin=True)
    map.connect('/status/modules/prod', controller='admin', action='modules', admin=False)
    map.connect('/admin/modules/prod', controller='admin', action='modules', admin=True)
    map.connect('/status/detectors/prod', controller='admin', action='detectors', admin=False)
    map.connect('/admin/detectors/prod', controller='admin', action='detectors', admin=True)
    map.connect('/status/readers/table', controller='admin', action='reader_status_table', admin=False)
    map.connect('/admin/readers/table', controller='admin', action='reader_status_table', admin=True)
    map.connect('/status/reader_history/{id}', controller='admin', action='reader_history', admin=False)
    map.connect('/admin/reader_history/{id}', controller='admin', action='reader_history', admin=True)
    map.connect('/status/reader_summary/{id}', controller='admin', action='reader_summary', admin=False)
    map.connect('/admin/reader_summary/{id}', controller='admin', action='reader_summary', admin=True)

    # manual. whoo
    map.connect('/sample/cnv/new', controller='sample', action="cnv_new")
    map.connect('/sample/cnv/create', controller='sample', action="cnv_create")
    map.connect('/sample/cnv/edit', controller='sample', action="cnv_edit")
    map.connect('/sample/cnv/save', controller='sample', action="cnv_save")
    map.connect('/sample/cnv/saved', controller='sample', action="cnv_saved")
    map.connect('/sample/cnv/delete', controller='sample', action="cnv_delete")

    # manual again, whoo -- go on scaffold?
    map.connect('/assay/enzyme/new', controller='assay', action='enzyme_conc_new')
    map.connect('/assay/enzyme/create', controller='assay', action='enzyme_conc_create')
    map.connect('/assay/enzyme/edit', controller='assay', action='enzyme_conc_edit')
    map.connect('/assay/enzyme/save', controller='assay', action='enzyme_conc_save')
    map.connect('/assay/enzyme/delete', controller='assay', action='enzyme_conc_delete')

    map.connect('/nplot/dg/runtime/bydate/{dg_id}', controller='nplot', action='dg_trend', prop='vacuum', view='time')
    map.connect('/nplot/dg/runtime/byrun/{dg_id}', controller='nplot', action='dg_trend', prop='vacuum', view='runs')
    map.connect('/nplot/dg/pressure/bydate/{dg_id}', controller='nplot', action='dg_trend', prop='pressure', view='time')
    map.connect('/nplot/dg/pressure/byrun/{dg_id}', controller='nplot', action='dg_trend', prop='pressure', view='runs')
    map.connect('/nplot/dg/spike/bydate/{dg_id}', controller='nplot', action='dg_trend', prop='spike', view='time')
    map.connect('/nplot/dg/spike/byrun/{dg_id}', controller='nplot', action='dg_trend', prop='spike', view='runs')

    map.connect('/plate/well_attr_csv/{id}/{attribute}', controller='plate', action='well_attr_csv')
    map.connect('/plate/well_metric_csv/{id}/{attribute}', controller='plate', action='well_metric_csv')
    map.connect('/plate/channel_attr_csv/{id}/{attribute}', controller='plate', action='channel_attr_csv')
    map.connect('/plate/channel_metric_csv/{id}/{attribute}', controller='plate', action='channel_metric_csv')
    map.connect('/plate/list/{id}', controller='plate', action='list_box2')

    map.connect('/well/gated/{id}', controller='well', action='threshold', show_only_gated=False)
    map.connect('/well/accepted_peak_csv/{id}', controller='well', action='peak_csv', show_only_gated=True)
    map.connect('/well/all_peak_csv/{id}', controller='well', action='peak_csv', show_only_gated=False)
    map.connect('/well/amphist/{id}/{channel_num}', controller='well', action='amphist')
    map.connect('/well/amptime/{id}/{channel_num}', controller='well', action='amptime')
    map.connect('/well/conc_trend/{id}/{channel_num}', controller='well', action='conc_trend')
    map.connect('/well/temporal_galaxy/{id}/{channel_num}', controller='well', action='temporal_galaxy')
    map.connect('/well/air_plot/{id}/{channel_num}', controller='well', action='air_plot')
    map.connect('/well/air_hist/{id}/{channel_num}', controller='well', action='air_hist')

    # TODO still seems kludgy
    map.connect('/setup', controller='setup', action='index')
    map.connect('/setup/', controller='setup', action='index')
    map.connect('/beta/{action}', controller='setup', beta=True)
    map.connect('/beta/{action}/{id}', controller='setup', beta=True)
    map.connect('/setup/{action}', controller='setup', beta=False)
    map.connect('/setup/{action}/{id}', controller='setup', beta=False)

    map.connect('/assay/new/{action}', controller='sequence', flow='sequence.new')
    map.connect('/assay/edit/{action}', controller='sequence', flow='sequence.edit')
    map.connect('/assay/approved', controller='sequence', action='approved_list')
    map.connect('/assay/group', controller='assay_group', action='list')
    map.connect('/assay/group/{action}', controller='assay_group')
    map.connect('/assay/view/{id}', controller='sequence', action='view_details')
    map.connect('/assay/view/{id}/sequences', controller='sequence', action='view_sequences')
    map.connect('/assay/view/{id}/plates', controller='sequence', action='view_plates')
    map.connect('/assay/view/{id}/validation', controller='sequence', action='view_validation')
    map.connect('/assay/{action}', controller='sequence')
    map.connect('/assay/{action}/{id}', controller='sequence')
    
    map.connect('/{controller}/{action}')
    map.connect('/{controller}/{action}/{id}')

    return map
