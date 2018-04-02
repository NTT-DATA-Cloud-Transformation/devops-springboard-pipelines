#!/usr/bin/env python


import boto3
import argparse
import os
import fnmatch
import datetime, time
import logging


def put_template_in_s3(client_s3,new_template_path):
    """
    To put the template in s3 bucket for product version creation
    :param client_s3:
    :param new_template_path:
    :return:
    """
    ntp=new_template_path
    logging.debug("new_template_path: {}".format(new_template_path))
    new_template_path = BUCKET_PATH+ "/" + new_template_path
    logging.debug("new_template_path: {}".format(new_template_path))
    filename_without_ext=new_template_path.split(".")[0]
    logging.debug("filename_without_ext: {}".format(filename_without_ext))
    logging.info("path for putting {}".format(filename_without_ext + "-git-hash-" +os.environ['CODEBUILD_RESOLVED_SOURCE_VERSION']+".yml"))
    response = client_s3.put_object( Body=open(ntp),Bucket=BUCKET_NAME,Key=filename_without_ext + "-git-hash-" +os.environ['CODEBUILD_RESOLVED_SOURCE_VERSION']+".yml")
    logging.info("new template uploaded to bucket")
    upload_path = filename_without_ext + "-git-hash-" +os.environ['CODEBUILD_RESOLVED_SOURCE_VERSION']+".yml"
    return upload_path


def parse_arguments():
    """
    To parse the command line arguments passed to script
    :return:
    """
    parser = argparse.ArgumentParser(description='Product Creation/Updation')
    parser.add_argument('--log_level', '-ll', default='WARN', type=str.upper,choices=['DEBUG', 'INFO', 'WARN', 'ERROR'],help='Set log level')
    parser.add_argument('--support_email', '-se', help='Support email for the service catalog products and portfolio', required=True)
    parser.add_argument('--bucket_name', '-bn', help='Bucket name for storing templates for products of service catalog', required=True)
    parser.add_argument('--bucket_path', '-bp', help='S3 bucket folder path for storing templates for products of service catalog like workshop/ecs-workshop', required=True)
    parser.add_argument('--portfolio_name', '-pn', help='Potfolio name under to which products are associated', required=True)
    parser.add_argument('--support_url', '-su', help='Support Url with http/https  like https://www.flux7.com ', required=True)
    args = parser.parse_args()
    return args


def configure_logging(log_level):
    """
    to set the logging level
    :param log_level:
    :return:
    """
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % log_level)

    logging.basicConfig(level = numeric_level)


def create_connection():
    """
    To create connection with aws for service catalog ans s3 client
    :return:
    """
    client_service_catalog = boto3.client('servicecatalog',region_name=REGION)
    client_s3= boto3.client('s3',region_name=REGION)
    return(client_service_catalog,REGION,client_s3)



def create_product(client,product_name,temp_s3_url):
    """
    To create the product
    :param client:
    :param product_name:
    :param temp_s3_url:
    :return:
    """
    logging.info("creating product")
    logging.info(temp_s3_url)
    logging.info(VERSION)
    logging.info(product_name)
    logging.debug("SUPPORT_EMAIL: {}".format(SUPPORT_EMAIL))
    logging.debug("SUPPORT_URL: {}".format(SUPPORT_URL))


    response = client.create_product(Name=product_name,Owner="flux7",Description="ecs-wrokshop",Distributor="flux7",SupportDescription="to enhance the code pipeline to use the service catalog",
                                     SupportEmail=SUPPORT_EMAIL,
                                     SupportUrl=SUPPORT_URL,
                                     ProductType='CLOUD_FORMATION_TEMPLATE',
                                     ProvisioningArtifactParameters={
                                         'Name': VERSION,
                                         'Description': 'initial version',
                                         'Info': {'LoadTemplateFromURL': temp_s3_url },
                                         'Type':'CLOUD_FORMATION_TEMPLATE'
                                     }
                                     )
    if  response['ProductViewDetail']['Status'] == 'CREATED':
        logging.info("product creation successful ")


    product_id = response['ProductViewDetail']['ProductViewSummary']['ProductId']
    product_version_id = response['ProvisioningArtifactDetail']['Id']
    product_version_name = response['ProvisioningArtifactDetail']['Name']
    return (product_id,product_version_id,product_version_name)


def create_version_of_product(client,version,temp_s3_url,product_id,product_name,region,client_s3):
    """
    To create the new version of product when there is a change in template
    :param client:
    :param version:
    :param temp_s3_url:
    :param product_id:
    :param product_name:
    :param region:
    :param client_s3:
    :return:
    """
    logging.info("version=",version)
    url ="{}/{}/".format(client_s3.meta.endpoint_url,BUCKET_NAME) + temp_s3_url

    logging.debug("URL: {}".format(url))
    response = client.create_provisioning_artifact(ProductId=product_id,
                                                   Parameters={
                                                       'Name': version,
                                                       'Info': {
                                                           'LoadTemplateFromURL': url
                                                       },
                                                       'Type':'CLOUD_FORMATION_TEMPLATE'
                                                   },
                                                   #IdempotencyToken=version
                                                   )

    logging.info("new version  {} created for product {} in region {}".format(version,product_name,region))




def create_portfolio(client,portfolio_name,region):
    """
    To create the portfolio
    :param client:
    :param portfolio_name:
    :param region:
    :return:
    """
    response = client.create_portfolio(
        DisplayName=portfolio_name,
        Description="for the ecs-workshop",
        ProviderName="flux7",

    )
    portfolio_id= response['PortfolioDetail']['Id']
    logging.info("portfolio {} created in region {}".format(portfolio_name,region))
    return portfolio_id

def attach_product_to_portfolio(client,product_id,portfolio_id):
    """
    To attach the product to portfolio
    :param client:
    :param product_id:
    :param portfolio_id:
    :return:
    """
    response = client.associate_product_with_portfolio(
        ProductId=product_id,
        PortfolioId=portfolio_id,
    )

def compare_templates(conn,template_url,product_name,product_template):
    """
    To compare the new and old template for same product and inform if there is any change in template.
    :param conn:
    :param template_url:
    :param product_name:
    :param product_template:
    :return:
    """
    client_s3 = conn[2]
    object_info_list=template_url.split("/",4)
    bucket=object_info_list[3]
    key=object_info_list[4].split(".yml")[0]+".yml"
    logging.debug("bucket: {}".format(bucket))
    logging.debug("key: {}".format(key))
    with open('temp_template.yml', 'wb') as data:
        client_s3.download_fileobj(bucket,key, data)

    old_template_path = 'temp_template.yml'
    new_template_path = 'cf-templates/{}/{}'.format(product_name,product_template)
    diff_set=set()
    with open(new_template_path) as f1, open(old_template_path) as f2:
        difference = set(f1).difference(f2)

    logging.debug("difference: {}".format(difference))
    if difference == diff_set:
        logging.debug("status: {}".format(False))
        logging.debug("old_template_path: {}".format(old_template_path))
        return (False,old_template_path)
    else:
        logging.debug("status: {}".format(True))
        logging.debug("new_template_path: {}".format(new_template_path))
        return (True,new_template_path)

def get_latest_version_template_from_product(ser_cat_clt_conn,latest_version_id,product_id):
    """
    TO get the latest template from product
    :param ser_cat_clt_conn:
    :param latest_version_id:
    :param product_id:
    :return:
    """
    response = ser_cat_clt_conn.describe_provisioning_artifact(ProvisioningArtifactId=latest_version_id,ProductId=product_id)
    logging.debug("latest template: {}".format(response['Info']['TemplateUrl']))
    return response['Info']['TemplateUrl']



def portfolio(ser_cat_clt_conn,region):
    """
    To search portfolio if it not present then create it.
    :param ser_cat_clt_conn:
    :param region:
    :return:
    """
    portfolio_dict = ser_cat_clt_conn.list_portfolios(PageSize=20)
    if portfolio_dict['PortfolioDetails']==[]:
        logging.info("creating portfolio {} in region {}".format(PORTFOLIO_NAME,region))
        portfolio_id = create_portfolio(ser_cat_clt_conn,PORTFOLIO_NAME,region)
    elif portfolio_dict['PortfolioDetails'] != []:
        for  portfolio in portfolio_dict['PortfolioDetails']:
            if portfolio['DisplayName']==PORTFOLIO_NAME:
                logging.info("portfolio {} already exist in region {}".format(PORTFOLIO_NAME,region))
                portfolio_id = portfolio['Id']
                break
        else:
            logging.info("creating portfolio {} in region {}".format(PORTFOLIO_NAME,region))
            portfolio_id = create_portfolio(ser_cat_clt_conn,PORTFOLIO_NAME,region)

    return portfolio_id

def main(temp_s3_url,product_name,conn,product_template,portfolio_id):
    """
    To calling the all methods as parent method
    :param temp_s3_url:
    :param product_name:
    :param conn:
    :param product_template:
    :param portfolio_id:
    :return:
    """
    ser_cat_clt_conn = conn[0]
    region = conn[1]
    client_s3 = conn[2]

    #TO create product

    response = ser_cat_clt_conn.search_products_as_admin(PortfolioId=portfolio_id)

    for product in response['ProductViewDetails']:
        logging.debug("found: {0} ".format(product['ProductViewSummary']['Name']))
        if product['ProductViewSummary']['Name'] == product_name:
            product_id =  product['ProductViewSummary']['ProductId']
            logging.debug("product_id: {}".format(product_id))
            version_response = ser_cat_clt_conn.describe_product_as_admin(Id=product_id)
            tdict= {}
            vdict= {}


            for version in  version_response['ProvisioningArtifactSummaries']:
                tdict[time.mktime(version['CreatedTime'].timetuple())]=version['Id']
                vdict[time.mktime(version['CreatedTime'].timetuple())]=version['Name']


            product_latest_version_id= tdict[max(tdict.keys())]
            product_latest_version_name= vdict[max(vdict.keys())]
            logging.debug("product_latest_version_id: {}".format(product_latest_version_id))
            logging.debug("product_latest_version_name: {}".format(product_latest_version_name))
            template_latest = get_latest_version_template_from_product(ser_cat_clt_conn,product_latest_version_id,product_id)
            logging.debug("product_template: {}".format(product_template))

            comp_status = compare_templates(conn,template_latest,product_name,product_template)

            # create version of product if template changed
            if comp_status[0] == True:
                global VERSION
                VERSION = "v"+str(float(product_latest_version_name.split("v")[1])+1)
                logging.info(VERSION)
                # upload new template to bucket for new version
                template_info = put_template_in_s3(client_s3,comp_status[1])
                create_version_of_product(ser_cat_clt_conn,VERSION,template_info,product_id,product_name,region,client_s3)

            break


    else:
        # TO upload template for product creation
        template_info = put_template_in_s3(client_s3,"cf-templates/{}/{}".format(product_name,product_template))
        url_path_without_s3_end_point=template_info
        s3_url ="{}/{}/".format(client_s3.meta.endpoint_url,BUCKET_NAME) + url_path_without_s3_end_point

        product_id,product_version_id,product_version_name =create_product(ser_cat_clt_conn,product_name,s3_url)
        logging.debug("product {} created in region {} with version {}".format(product_name,region,product_version_name))
        #TO associate the product with portfolio
        attach_product_to_portfolio(ser_cat_clt_conn,product_id,portfolio_id)
        logging.debug("product {} attached with portfolio {}".format(product_name,PORTFOLIO_NAME))


if __name__ == "__main__":
    # To get the parsed arguments
    ARGS = parse_arguments()
    configure_logging(ARGS.log_level)
    SUPPORT_EMAIL = ARGS.support_email
    BUCKET_NAME = ARGS.bucket_name
    BUCKET_PATH = ARGS.bucket_path
    PORTFOLIO_NAME = ARGS.portfolio_name
    REGION = os.environ['AWS_DEFAULT_REGION']
    SUPPORT_URL = ARGS.support_url

    product_name_list=os.listdir('cf-templates')
    logging.info(product_name_list)
    conn = create_connection()
    ser_cat_clt_conn = conn[0]
    region = conn[1]
    client_s3 = conn[2]
    # To create portfolio
    portfolio_id = portfolio(ser_cat_clt_conn,region)

    for product_name in product_name_list:
        VERSION = "v1.0"
        product_template=fnmatch.filter(os.listdir('cf-templates/{}'.format(product_name)), '*.yml')[0]
        product_temp_s3_url='{}/{}/{}'.format(client_s3.meta.endpoint_url,BUCKET_NAME,"{}/cf-templates/{}/{}".format(BUCKET_PATH,product_name,product_template))
        logging.info(product_temp_s3_url)
        logging.info("product_name={}".format(product_name))
        logging.debug("product template name: {}/{}\n".format(product_name,product_template))
        # To create product one by one.
        main(product_temp_s3_url,product_name,conn,product_template,portfolio_id)


