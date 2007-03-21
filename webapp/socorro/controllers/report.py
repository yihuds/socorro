from socorro.lib.base import *
from socorro.lib.collect import Collector, FixupSourcePath, TempFileForData
import socorro.models as model

class ReportController(BaseController):
  def index(self):
    c.report = model.CrashReport.get_by(crash_id=request.params['crash'])
    return render_response('report_index')

  def list(self):
    c.reports = model.CrashReport.select()
    return render_response('report_list')

  def add(self):
    if request.environ['REQUEST_METHOD'] == 'POST':
      # get a handle on the situation
      symbol_dir = g.pylons_config.app_conf['socorro.symbol_dir']
      minidump = g.pylons_config.app_conf['socorro.minidump_stackwalk']
      collector = Collector(minidump, [symbol_dir])
      crash_dump = request.POST['upload_file_minidump']
      if not crash_dump.file:
        return Response('Bad request')
      
      # now parse out the data
      try:   
        tempfile = TempFileForData(crash_dump.value)
        fh = collector.breakpad_file(tempfile)

        # read report headers
        report = model.CrashReport()
        report.read_header(fh)
        report.flush()
        
        # record each stack frame of the crash
        #XXXsayrer probably not real fast to flush after each one
        for line in fh:
          frame = model.StackFrame()
          frame.readline(line[:-1])
          if frame.source is not None:
            frame.source = FixupSourcePath(frame.source)
          frame.crash_id = report.crash_id
          frame.flush()
	  
      finally:
        tempfile.close()

      return Response(report.crash_id)
    else:
      h.log('bad request?')
      #XXXsayrer set a 4xx status
      return Response('Bad request')
