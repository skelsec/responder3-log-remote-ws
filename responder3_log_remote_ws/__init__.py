import asyncio
import websockets
import uuid
import ssl
import itertools

from responder3.core.logtask import *
from responder3.core.commons import *
from responder3.core.gwss import *
from responder3.core.ssl import SSLContextBuilder
	

class R3RemoteWSClient:
	def __init__(self, logQ, server_url, log_queue_out, ssl_ctx = None):
		self.logger = Logger('R3RemoteWSClient', logQ = logQ)
		self.client_out = asyncio.Queue()
		self.client = GenericWSClient(logQ, server_url, self.client_out, ssl_ctx = ssl_ctx)
		self.log_queue_out = log_queue_out
		self.shutdown_evt = asyncio.Event()
		
	@r3exception
	async def run(self):
		asyncio.ensure_future(self.client.run())
		while True:
			log_obj = await self.log_queue_out.get()
			log_obj_type = logobj2type_inv[type(log_obj)]
			rlog = R3CliLog(log_obj_type = log_obj_type, log_obj = log_obj)
			rlog.remote_ip = 'test'
			rlog.remote_port = 0
				
			await self.client_out.put(rlog.to_json())

			
class R3RemoteWSServer:
	def __init__(self, logQ, listen_ip, listen_port, log_queue_in,  ssl_ctx = None):
		self.logger = Logger('R3RemoteWSServer', logQ = logQ)
		self.listen_ip = listen_ip
		self.listen_port = listen_port
		self.ssl_ctx = ssl_ctx
		self.log_queue_in = log_queue_in
		self.shutdown_evt = asyncio.Event()
		self.shutdown_session_evt = asyncio.Event()
		self.classloader = R3ClientCommsClassLoader()
		self.server_queue_in = asyncio.Queue()
		self.is_NATed = False
		
		self.server = GenericWSServer(logQ, listen_ip, listen_port, self.server_queue_in, ssl_ctx = ssl_ctx)
	
	@r3exception
	async def handle_logs(self):
		while True:
			gp = await self.server_queue_in.get()
			msg = self.classloader.from_json(gp.data)
			if isinstance(msg, R3CliLog):
				if self.is_NATed == False:
					msg.remote_ip = gp.client_ip
					msg.remote_port = gp.client_port
				else:
					msg.remote_ip = msg.remote_ip
					msg.remote_port = msg.remote_port
				
				if not gp.client_cert:
					msg.client_id = gp.get_addr_s()
				else:
					#https://stackoverflow.com/questions/50548709/cant-receive-tls-certificate-using-getpeercert-ssl-certificate-verify-failed
					#I have no idea how this works tho
					client_cn = dict(itertools.chain(*gp.client_cert["subject"]))["commonName"]
					msg.client_id = client_cn
				await self.log_queue_in.put(msg)
			else:
				await self.logger.debug('Unknown message sent by the client!')		
	
	@r3exception
	async def run(self):
		asyncio.ensure_future(self.server.run())
		await self.handle_logs()
	
		
class remote_wsHandler(LoggerExtensionTask):
	def init(self):
		try:
			self.logger = Logger('remote_wsHandler', logQ = self.log_queue)
			
			self.mode = self.config['mode']
			if self.mode == 'SERVER':
				self.listen_ip = self.config['listen_ip']
				self.listen_port = self.config['listen_port']
				self.ssl_ctx = None
				if 'ssl_ctx' in self.config:
					self.ssl_ctx = SSLContextBuilder.from_dict(self.config['ssl_ctx'])
				
				
				self.handler = R3RemoteWSServer(self.log_queue, self.listen_ip, self.listen_port, self.log_queue,  ssl_ctx = self.ssl_ctx)
			
			elif self.mode == 'CLIENT':
				self.server_url = self.config['server_url']
				if 'ssl_ctx' in self.config:
					self.ssl_ctx = SSLContextBuilder.from_dict(self.config['ssl_ctx'])
				
				self.handler = R3RemoteWSClient(self.log_queue, self.server_url, self.result_queue, ssl_ctx = self.ssl_ctx)
			
			else:
				raise Exception('Unknown mode!')
			
		except Exception as e:
			traceback.print_exc()

	async def main(self):
		print('handler')
		await self.handler.run() 
		
	async def setup(self):
		pass
