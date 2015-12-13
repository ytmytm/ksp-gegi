
def time_format(sec):
	days = int(sec / (24 * 60 * 60))
	sec = sec - days*24*60*60
	hours = int(sec / (60 * 60))
	sec = sec - hours*60*60
	minutes = int(sec / 60)
	sec = int(sec - minutes*60)

	if days>=100:
		return "{:5d}d".format(days)
	if days>0:
		return "{:2d}d".format(days)+"{:02d}h".format(hours)
	if hours>0:
		return "{:2d}h".format(hours)+"{:02d}m".format(minutes)
	if minutes>0:
		return "{:2d}m".format(minutes)+"{:02d}s".format(sec)
	return "{:5d}s".format(sec)
