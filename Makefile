all: rebuild

clean:
	rm -f dump bulkloader-* *.pyc

upload:
	cat .gaepass | appcfg.py -e "$(MAIL)" --passin update .

serve: .tmp/blobstore
	dev_appserver.py --enable_sendmail --use_sqlite --blobstore_path=.tmp/blobstore --datastore_path=.tmp/datastore -a 0.0.0.0 .

.tmp/blobstore:
	mkdir -p .tmp/blobstore
